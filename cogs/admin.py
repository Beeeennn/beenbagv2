# cogs/admin.py
import re
import logging
from typing import List, Optional

import discord
from discord.ext import commands

from config import settings
from db.pool import get_pool  # optional, we mainly use self.bot.db_pool
from tasks.spawns import start_guild_spawn_task, spawn_once_in_channel
from utils.prefixes import warm_prefix_cache, get_cached_prefix  # cache helpers

# --------- Channel token parsing (mention / link / id) ---------
# Accepts: <#123>, https://discord.com/channels/GUILD/123, or 123
_CHANNEL_TOKEN_RE = re.compile(
    r"(?:<#(?P<m>\d{15,25})>|https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/\d{15,25}/(?P<u>\d{15,25})|\b(?P<i>\d{15,25})\b)"
)


def _extract_first_channel_id(text: str) -> Optional[int]:
    if not text:
        return None
    m = _CHANNEL_TOKEN_RE.search(text)
    if not m:
        return None
    s = m.group("m") or m.group("u") or m.group("i")
    try:
        return int(s)
    except Exception:
        return None


def _resolve_channel_from_text(ctx: commands.Context, text: Optional[str]):
    """Return a TextChannel/Thread from mention/link/id text; or None."""
    cid = _extract_first_channel_id(text or "")
    if not cid:
        return None
    ch = ctx.guild.get_channel(cid) or ctx.bot.get_channel(cid)
    return ch


def _bot_can_send(ctx: commands.Context, ch) -> bool:
    me = ctx.guild.me
    if not me:
        return False
    perms = ch.permissions_for(me)
    # Threads may need send_messages_in_threads
    return perms.view_channel and (getattr(perms, "send_messages_in_threads", False) or perms.send_messages)


def _bot_can_react(ctx: commands.Context, ch) -> bool:
    me = ctx.guild.me
    if not me:
        return False
    perms = ch.permissions_for(me)
    # For threads, Add Reactions is still the key
    return perms.view_channel and perms.add_reactions


def parse_channel_ids_any(bot: commands.Bot, msg: discord.Message) -> List[int]:
    ids = set()
    for m in _CHANNEL_TOKEN_RE.finditer(msg.content):
        cid = m.group("m") or m.group("u") or m.group("i")
        if cid:
            try:
                cid_i = int(cid)
            except ValueError:
                continue
            ch = msg.guild.get_channel(cid_i) or bot.get_channel(cid_i)
            if ch and ch.guild.id == msg.guild.id:
                ids.add(cid_i)
    return list(ids)


def parse_one_channel_id_any(bot: commands.Bot, msg: discord.Message) -> Optional[int]:
    ids = parse_channel_ids_any(bot, msg)
    return ids[0] if ids else None


DEFAULT_PREFIX = settings.DEFAULT_PREFIX  # "bc!"


def sanitize_prefix(raw: Optional[str]) -> Optional[str]:
    """Return a cleaned prefix or None if invalid."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > 8:  # keep it reasonable
        return None
    if any(ch.isspace() for ch in s):
        return None
    return s


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot  # expects bot.db_pool to be set

    # ---------- small SQL helpers for bigint[] columns ----------
    @staticmethod
    async def _array_add(conn, guild_id: int, column: str, value: int):
        # allow link/game/react channel id arrays
        if column not in ("link_channel_ids", "game_channel_ids", "react_channel_ids"):
            raise ValueError("invalid column")
        await conn.execute(
            f"""
            INSERT INTO guild_settings (guild_id, {column})
            VALUES ($1, ARRAY[$2]::bigint[])
            ON CONFLICT (guild_id) DO UPDATE
            SET {column} = (
              SELECT ARRAY(
                SELECT DISTINCT e FROM unnest(coalesce(guild_settings.{column}, '{{}}'::bigint[]) || ARRAY[$2]::bigint[]) AS t(e)
              )
            )
            """,
            guild_id, value
        )

    @staticmethod
    async def _array_remove(conn, guild_id: int, column: str, value: int):
        if column not in ("link_channel_ids", "game_channel_ids", "react_channel_ids"):
            raise ValueError("invalid column")
        await conn.execute(
            f"""
            INSERT INTO guild_settings (guild_id, {column})
            VALUES ($1, '{{}}'::bigint[])
            ON CONFLICT (guild_id) DO UPDATE
            SET {column} = array_remove(coalesce(guild_settings.{column}, '{{}}'::bigint[]), $2)
            """,
            guild_id, value
        )

    # ---------- Welcome on/off ----------
    @commands.command(name="enablewelcome", aliases=["welcomeon"])
    @commands.has_permissions(administrator=True)
    async def enable_welcome(self, ctx: commands.Context):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, welcome_enabled)
                VALUES ($1, TRUE)
                ON CONFLICT (guild_id) DO UPDATE SET welcome_enabled = EXCLUDED.welcome_enabled
                """,
                ctx.guild.id
            )
        await ctx.send("✅ Welcome messages **enabled**. New members will be greeted in the announce channel (if set).")

    @commands.command(name="disablewelcome", aliases=["welcomeoff"])
    @commands.has_permissions(administrator=True)
    async def disable_welcome(self, ctx: commands.Context):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, welcome_enabled)
                VALUES ($1, FALSE)
                ON CONFLICT (guild_id) DO UPDATE SET welcome_enabled = EXCLUDED.welcome_enabled
                """,
                ctx.guild.id
            )
        await ctx.send("✅ Welcome messages **disabled** for this server.")
    @commands.command(name="addmilestone")
    @commands.has_guild_permissions(manage_guild=True)
    async def add_milestone(self, ctx: commands.Context, level: int, role: discord.Role):
        """Admin-only: map a level to a role in guild_level_roles."""
        if level <= 0:
            return await ctx.send("❌ Level must be a positive integer.")

        # sanity: can the bot assign this role?
        me = ctx.guild.me
        warn = None
        if not me.guild_permissions.manage_roles:
            warn = "⚠️ I don't have **Manage Roles**, so I won't be able to assign this role on level-up."
        elif role >= me.top_role:
            warn = f"⚠️ **{role.name}** is higher/equal to my top role; I can't assign it. Move my role above it."

        # upsert into DB
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_level_roles (guild_id, level, role_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (guild_id, level)
                DO UPDATE SET role_id = EXCLUDED.role_id
                """,
                ctx.guild.id, level, role.id
            )
        msg = f"✅ Milestone set: **Level {level} → {role.mention}**."
        if warn:
            msg += f"\n{warn}"
        await ctx.send(msg)
    @commands.command(name="removemilestone")
    @commands.has_guild_permissions(manage_guild=True)
    async def remove_milestone(self, ctx: commands.Context, level: int):
        async with self.bot.db_pool.acquire() as conn:
            done = await conn.execute(
                "DELETE FROM guild_level_roles WHERE guild_id=$1 AND level=$2",
                ctx.guild.id, level
            )
        if done.endswith("0"):
            return await ctx.send(f"ℹ️ No milestone found at level **{level}**.")
        await ctx.send(f"🗑️ Removed milestone for **Level {level}**.")



    # ---------- Setup wizard ----------
    @commands.command(name="setupbot", aliases=["setup"])
    @commands.has_permissions(administrator=True)
    async def setup_bot(self, ctx: commands.Context):
        guild_id = ctx.guild.id

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel

        async with self.bot.db_pool.acquire() as conn:
            # 1) Command prefix
            await ctx.send("**Welcome to the beenbag bot setup!!**\n"
                           "Don't worry if you make a mistake, all of these setting can be changed later.\n"
                           "See how in admin section of `!help`, after finishing setup\n"
                           "It runs most smoothly if nothing else is said in the chat until it's over\n"
                            "**1/7** What **command prefix** should I use? (e.g. `!`, `bc!`, `$`). Type `default` to use `bc!`.")
            msg = await self.bot.wait_for("message", check=check)
            raw = msg.content.strip()
            if raw.lower() == "default":
                command_prefix = DEFAULT_PREFIX
            else:
                command_prefix = sanitize_prefix(raw) or DEFAULT_PREFIX
                if command_prefix == DEFAULT_PREFIX and raw.lower() != "default":
                    await ctx.send("❌ Invalid prefix. Using default `!`.")

            # 2) Spawn channels
            await ctx.send("**2/7** Use `#` to mention the **channels for mob spawns** (space/comma separated), or type `none` to skip. Its reccomended to have a cooldown of about 2 seconds in these channels:")
            msg = await self.bot.wait_for("message", check=check)
            spawn_channels = parse_channel_ids_any(self.bot, msg) if msg.content.strip().lower() != "none" else []

            # 3) Announce channel
            await ctx.send("**3/7** Use `#` to mention the **announce channel** (level ups, welcomes), or type `none` to skip:")
            msg = await self.bot.wait_for("message", check=check)
            announce_channel_id = parse_one_channel_id_any(self.bot, msg) if msg.content.strip().lower() != "none" else None

            await ctx.send("**4/8** Enable **level-up announcements**? (`yes`/`no`) Default: `yes`")
            msg = await self.bot.wait_for("message", check=check)
            lvl_ann = msg.content.strip().lower() not in {"no", "n", "off", "false", "0"}

            # 4) Link channels
            await ctx.send("**4/7** Use `#` to mention the **link channels** (space/comma) where the bot can send links, or type `none` to skip:")
            msg = await self.bot.wait_for("message", check=check)
            link_channel_ids = parse_channel_ids_any(self.bot, msg) if msg.content.strip().lower() != "none" else []

            # 5) React channels
            await ctx.send("**5/7** Use `#` to mention the **react channels** (space/comma) where the bot can auto-react, or type `none` to skip:")
            msg = await self.bot.wait_for("message", check=check)
            react_channel_ids = parse_channel_ids_any(self.bot, msg) if msg.content.strip().lower() != "none" else []

            # 6) Game channels
            await ctx.send("**6/7** Mention the **game channels** (space/comma) where game commands are allowed, or type `none` to allow anywhere:")
            msg = await self.bot.wait_for("message", check=check)
            game_channel_ids = parse_channel_ids_any(self.bot, msg) if msg.content.strip().lower() != "none" else []

            # 7) Log channel
            await ctx.send("**7/7** Mention the **log channel** (admin logs), or type `none` to skip:")
            msg = await self.bot.wait_for("message", check=check)
            log_channel_id = parse_one_channel_id_any(self.bot, msg) if msg.content.strip().lower() != "none" else None

            
            await conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id,
                    announce_channel_id,
                    link_channel_ids,
                    react_channel_ids,
                    game_channel_ids,
                    log_channel_id,
                    command_prefix,
                    level_announcements_enabled
                ) VALUES ($1, $2, $3::bigint[], $4::bigint[], $5::bigint[], $6, $7, $8)
                ON CONFLICT (guild_id) DO UPDATE
                SET announce_channel_id           = EXCLUDED.announce_channel_id,
                    link_channel_ids              = EXCLUDED.link_channel_ids,
                    react_channel_ids             = EXCLUDED.react_channel_ids,
                    game_channel_ids              = EXCLUDED.game_channel_ids,
                    log_channel_id                = EXCLUDED.log_channel_id,
                    command_prefix                = EXCLUDED.command_prefix,
                    level_announcements_enabled   = EXCLUDED.level_announcements_enabled
                """,
                guild_id,
                announce_channel_id,
                link_channel_ids,
                react_channel_ids,
                game_channel_ids,
                log_channel_id,
                command_prefix,
                lvl_ann,
            )
            # Replace spawn channels
            await conn.execute("DELETE FROM guild_spawn_channels WHERE guild_id = $1", guild_id)
            for ch_id in spawn_channels:
                await conn.execute(
                    "INSERT INTO guild_spawn_channels (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    guild_id, ch_id
                )

        # refresh prefix cache globally so it takes effect immediately
        await warm_prefix_cache(self.bot.db_pool)

        await ctx.send(
            f"✅ Setup complete! Using prefix **`{command_prefix}`**\n"
            "• spawn channels saved\n"
            "• announce channel saved\n"
            "• link channels saved\n"
            "• react channels saved\n"
            "• game channels saved\n"
            "• log channel saved\n"
            "**NEXT STEPS:**"
            f"• use `{command_prefix}addmilestione <level> <@role>` to add roles when a user gets to a certain level\n"
            f"• you can use `{command_prefix}disablewelcome` to disable to welcom message which @ new users. Other admin commands can be seen in help menu"
        )

        # refresh this guild's spawner to pick up changes
        start_guild_spawn_task(self.bot, guild_id)
    # ---------- Announce channel ----------
    @commands.command(name="setannouncechannel", aliases=["setannounce", "announcechannel"])
    @commands.has_permissions(administrator=True)
    async def setannouncechannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """
        Set the announce channel for this server (level-ups, welcomes).
        Use in a channel with no args to set it to the current channel,
        or mention a channel to target it, e.g. `#announcements`.
        """
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = channel or ctx.channel

        # sanity: must be in this guild
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")

        me = ctx.guild.me
        perms = target.permissions_for(me)
        can_send = perms.send_messages or getattr(perms, "send_messages_in_threads", False)
        if not (perms.view_channel and can_send):
            return await ctx.send(f"❌ I don’t have permission to post in {target.mention}.")

        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, announce_channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE
                SET announce_channel_id = EXCLUDED.announce_channel_id
                """,
                ctx.guild.id, target.id
            )

        await ctx.send(f"✅ Announce channel set to {target.mention}.")

    @setannouncechannel.error
    async def setannouncechannel_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                f"❌ I couldn't find that channel. "
                f"Use `{ctx.clean_prefix}setannouncechannel` in the target channel, or mention it like `#announcements`."
            )
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ You need the **Administrator** permission to do that.")
        raise error

    # ---------- Set prefix (quick) ----------
    @commands.command(name="setprefix", aliases=["prefix"])
    @commands.has_permissions(administrator=True)
    async def setprefix(self, ctx: commands.Context, *, new_prefix: Optional[str] = None):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        guild_id = ctx.guild.id

        # Show current prefix if no argument given
        if new_prefix is None:
            current = get_cached_prefix(guild_id) or DEFAULT_PREFIX
            return await ctx.send(
                f"Current prefix here is **`{current}`**.\n"
                f"Change it with `@{self.bot.user.name} setprefix <new>` or `{current}setprefix <new>`.\n"
                f"Use `setprefix default` to reset."
            )

        # Handle reset/default
        if new_prefix.lower() in ("default", "reset"):
            prefix = DEFAULT_PREFIX
        else:
            prefix = sanitize_prefix(new_prefix)
            if not prefix:
                return await ctx.send("❌ Invalid prefix. Use 1–8 non-space characters. Example: `!`, `bc!`, `$`")

        # Persist
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, command_prefix)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE
                SET command_prefix = EXCLUDED.command_prefix
                """,
                guild_id, prefix
            )

        # Refresh cache
        await warm_prefix_cache(self.bot.db_pool)

        await ctx.send(f"✅ Prefix updated to **`{prefix}`**. You can now use `{prefix}help`.")
    
    @commands.command(name="levelannounce", aliases=["levelsannounce","togglelevels"])
    @commands.has_guild_permissions(manage_guild=True)
    @commands.guild_only()
    async def level_announce(self, ctx: commands.Context, state: str):
        s = state.strip().lower()
        if s in {"on","enable","enabled","true","yes","y","1"}:
            flag = True
        elif s in {"off","disable","disabled","false","no","n","0"}:
            flag = False
        else:
            return await ctx.send("Usage: `levelannounce <on|off>`")

        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, level_announcements_enabled)
                VALUES ($1, $2)
                ON CONFLICT (guild_id)
                DO UPDATE SET level_announcements_enabled = EXCLUDED.level_announcements_enabled
                """,
                ctx.guild.id, flag
            )

        await ctx.send(f"✅ Level-up announcements are now **{'enabled' if flag else 'disabled'}**.")

    # ---------- Logs channel ----------
    @commands.command(name="setlogs", aliases=["setlog", "logs"])
    @commands.has_permissions(administrator=True)
    async def setlogs(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """
        Set the logs channel for this server.
        Use in a channel with no args to set it to the current channel,
        or mention a channel to target it, e.g. `#logs`.
        """
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = channel or ctx.channel

        # sanity: make sure it's in this guild and bot can post there
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")
        me = ctx.guild.me
        perms = target.permissions_for(me)
        if not (perms.view_channel and (perms.send_messages or getattr(perms, "send_messages_in_threads", False))):
            return await ctx.send(f"❌ I don’t have permission to post in {target.mention}.")

        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, log_channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE
                SET log_channel_id = EXCLUDED.log_channel_id
                """,
                ctx.guild.id, target.id
            )

        await ctx.send(f"✅ Log channel set to {target.mention}.")

    @setlogs.error
    async def setlogs_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                f"❌ I couldn't find that channel. "
                f"Use `{ctx.clean_prefix}setlogs` in the target channel, or mention it like `#logs`."
            )
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ You need the **Administrator** permission to do that.")
        raise error

    # ---------- Spawn channels (add/remove/list) ----------
    @commands.command(name="addspawnchannel", aliases=["addspawn", "addspawnhannel"])  # last alias covers the typo just in case
    @commands.has_permissions(administrator=True)
    async def addspawnchannel(
        self, ctx: commands.Context, channel: Optional[discord.abc.GuildChannel] = None
    ):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = channel or ctx.channel

        # Only allow text channels or threads
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")

        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")

        me = ctx.guild.me
        perms = target.permissions_for(me)
        can_send = perms.send_messages or getattr(perms, "send_messages_in_threads", False)
        if not (perms.view_channel and can_send):
            return await ctx.send(f"❌ I don’t have permission to post in {target.mention}.")

        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_spawn_channels (guild_id, channel_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                ctx.guild.id, target.id
            )

        # refresh this guild's spawner to pick up the change
        start_guild_spawn_task(self.bot, ctx.guild.id)

        await ctx.send(f"✅ Added {target.mention} as a spawn channel.")

    @addspawnchannel.error
    async def addspawnchannel_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            return await ctx.send(
                f"❌ I couldn't find that channel. "
                f"Use `{ctx.clean_prefix}addspawnchannel` in the target channel, or mention it like `#spawns`."
            )
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ You need the **Administrator** permission to do that.")
        raise error

    @commands.command(name="removespawnchannel", aliases=["removespawn", "delspawn"])
    @commands.has_permissions(administrator=True)
    async def removespawnchannel(
        self, ctx: commands.Context, channel: Optional[discord.abc.GuildChannel] = None
    ):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = channel or ctx.channel

        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")

        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")

        async with self.bot.db_pool.acquire() as conn:
            res = await conn.execute(
                "DELETE FROM guild_spawn_channels WHERE guild_id = $1 AND channel_id = $2",
                ctx.guild.id, target.id
            )

        # res is like "DELETE 0" or "DELETE 1"
        deleted = res.endswith("1")

        # refresh this guild's spawner to pick up the change
        start_guild_spawn_task(self.bot, ctx.guild.id)

        if deleted:
            await ctx.send(f"✅ Removed {target.mention} from spawn channels.")
        else:
            await ctx.send(f"ℹ️ {target.mention} wasn’t a spawn channel.")

    # ---------- Link channels ----------
    @commands.command(name="addlinkchannel", aliases=["addlink", "addlinkch"])
    @commands.has_permissions(administrator=True)
    async def addlinkchannel(self, ctx: commands.Context, *, channel_text: Optional[str] = None):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = _resolve_channel_from_text(ctx, channel_text) or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")
        if not _bot_can_send(ctx, target):
            return await ctx.send(f"❌ I don’t have permission to post in {target.mention}.")

        async with self.bot.db_pool.acquire() as conn:
            await self._array_add(conn, ctx.guild.id, "link_channel_ids", target.id)

        await ctx.send(f"✅ Added {target.mention} to **link channels**.")

    @commands.command(name="removelinkchannel", aliases=["removelink", "dellink"])
    @commands.has_permissions(administrator=True)
    async def removelinkchannel(self, ctx: commands.Context, *, channel_text: Optional[str] = None):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = _resolve_channel_from_text(ctx, channel_text) or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")

        async with self.bot.db_pool.acquire() as conn:
            await self._array_remove(conn, ctx.guild.id, "link_channel_ids", target.id)

        await ctx.send(f"✅ Removed {target.mention} from **link channels** (if it was set).")

    @commands.command(name="linkchannels", aliases=["listlinks"])
    @commands.has_permissions(administrator=True)
    async def linkchannels(self, ctx: commands.Context):
        async with self.bot.db_pool.acquire() as conn:
            ids = await conn.fetchval(
                "SELECT link_channel_ids FROM guild_settings WHERE guild_id=$1",
                ctx.guild.id
            )
        ids = ids or []
        if not ids:
            return await ctx.send("ℹ️ No link channels configured.")
        mentions = []
        for cid in ids:
            ch = ctx.guild.get_channel(cid) or self.bot.get_channel(cid)
            mentions.append(ch.mention if ch else f"`{cid}` (missing)")
        await ctx.send("🔗 Link channels:\n• " + "\n• ".join(mentions))

    # ---------- Game channels ----------
    @commands.command(name="addgamechannel", aliases=["addgame", "addgamech"])
    @commands.has_permissions(administrator=True)
    async def addgamechannel(self, ctx: commands.Context, *, channel_text: Optional[str] = None):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = _resolve_channel_from_text(ctx, channel_text) or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")
        if not _bot_can_send(ctx, target):
            return await ctx.send(f"❌ I don’t have permission to post in {target.mention}.")

        async with self.bot.db_pool.acquire() as conn:
            await self._array_add(conn, ctx.guild.id, "game_channel_ids", target.id)

        await ctx.send(f"✅ Added {target.mention} to **game channels**.")

    @commands.command(name="removegamechannel", aliases=["removegame", "delgame"])
    @commands.has_permissions(administrator=True)
    async def removegamechannel(self, ctx: commands.Context, *, channel_text: Optional[str] = None):
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = _resolve_channel_from_text(ctx, channel_text) or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")

        async with self.bot.db_pool.acquire() as conn:
            await self._array_remove(conn, ctx.guild.id, "game_channel_ids", target.id)

        await ctx.send(f"✅ Removed {target.mention} from **game channels** (if it was set).")

    @commands.command(name="gamechannels", aliases=["listgames"])
    @commands.has_permissions(administrator=True)
    async def gamechannels(self, ctx: commands.Context):
        async with self.bot.db_pool.acquire() as conn:
            ids = await conn.fetchval(
                "SELECT game_channel_ids FROM guild_settings WHERE guild_id=$1",
                ctx.guild.id
            )
        ids = ids or []
        if not ids:
            return await ctx.send("ℹ️ No game channels configured. (If empty, game commands are allowed anywhere.)")
        mentions = []
        for cid in ids:
            ch = ctx.guild.get_channel(cid) or self.bot.get_channel(cid)
            mentions.append(ch.mention if ch else f"`{cid}` (missing)")
        await ctx.send("🎮 Game channels:\n• " + "\n• ".join(mentions))

    # ---------- React channels ----------
    @commands.command(name="addreactchannel", aliases=["addreact", "addreactch"])
    @commands.has_permissions(administrator=True)
    async def addreactchannel(self, ctx: commands.Context, *, channel_text: Optional[str] = None):
        """Add a channel where the bot is allowed to auto-react."""
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = _resolve_channel_from_text(ctx, channel_text) or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")
        if not _bot_can_react(ctx, target):
            return await ctx.send(f"❌ I don’t have permission to react in {target.mention}.")

        async with self.bot.db_pool.acquire() as conn:
            await self._array_add(conn, ctx.guild.id, "react_channel_ids", target.id)

        await ctx.send(f"✅ Added {target.mention} to **react channels**.")

    @commands.command(name="removereactchannel", aliases=["removereact", "delreact"])
    @commands.has_permissions(administrator=True)
    async def removereactchannel(self, ctx: commands.Context, *, channel_text: Optional[str] = None):
        """Remove a channel from the bot’s auto-react list."""
        if ctx.guild is None:
            return await ctx.send("❌ This command can only be used in a server.")

        target = _resolve_channel_from_text(ctx, channel_text) or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await ctx.send("❌ Please choose a text channel or a thread.")
        if target.guild.id != ctx.guild.id:
            return await ctx.send("❌ That channel isn’t in this server.")

        async with self.bot.db_pool.acquire() as conn:
            await self._array_remove(conn, ctx.guild.id, "react_channel_ids", target.id)

        await ctx.send(f"✅ Removed {target.mention} from **react channels** (if it was set).")

    @commands.command(name="reactchannels", aliases=["listreact"])
    @commands.has_permissions(administrator=True)
    async def reactchannels(self, ctx: commands.Context):
        """List configured react channels."""
        async with self.bot.db_pool.acquire() as conn:
            ids = await conn.fetchval(
                "SELECT react_channel_ids FROM guild_settings WHERE guild_id=$1",
                ctx.guild.id
            )
        ids = ids or []
        if not ids:
            return await ctx.send("ℹ️ No react channels configured.")
        mentions = []
        for cid in ids:
            ch = ctx.guild.get_channel(cid) or self.bot.get_channel(cid)
            mentions.append(ch.mention if ch else f"`{cid}` (missing)")
        await ctx.send("😄 React channels:\n• " + "\n• ".join(mentions))


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
