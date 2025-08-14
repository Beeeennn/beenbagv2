# cogs/events.py
from discord.ext import commands
import logging
from utils.prefixes import get_cached_prefix
from utils.game_helpers import gain_exp,ensure_player,sucsac,lb_inc
from tasks.spawns import start_all_guild_spawn_tasks, start_guild_spawn_task, stop_guild_spawn_task
from tasks.fish_food import give_fish_food_task
from services import achievements,barn
from datetime import datetime, timezone
import random
from constants import MOBS,RARITIES,COLOR_MAP
import discord
import asyncio
from config import settings

chat_xp_cd = commands.CooldownMapping.from_cooldown(
    2,                # max tokens
    1800.0,           # per 1800 seconds (30m)
    commands.BucketType.user
)
class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ready_once = False

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✅ Logged in as {self.bot.user} ({self.bot.user.id})")
        #await self.bot.change_presence(activity=discord.Game("DEV: local build"))
        # achievements schema first (safe re-run)
        from services import achievements
        await achievements.ensure_schema(self.bot.db_pool)
        await achievements.sync_master(self.bot.db_pool)

        # start spawn tasks only in the right environment
        for g in self.bot.guilds:
            if settings.IS_DEV:
                if g.id in settings.TEST_GUILDS:
                    start_guild_spawn_task(self.bot, g.id)
            else:
                if g.id not in settings.TEST_GUILDS:
                    start_guild_spawn_task(self.bot, g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        start_guild_spawn_task(self.bot, guild.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        stop_guild_spawn_task(self.bot, guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member):

        guild = member.guild

        # read setting (default TRUE) + preferred channel
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(welcome_enabled, TRUE) AS welcome_enabled,
                    announce_channel_id
                FROM guild_settings
                WHERE guild_id = $1
                """,
                guild.id
            )

        if row and not row["welcome_enabled"]:
            return  # welcomes disabled

        # pick channel: announce_channel_id → system_channel → first text channel we can speak in
        channel = None
        if row and row["announce_channel_id"]:
            channel = guild.get_channel(row["announce_channel_id"])
            if channel and not channel.permissions_for(guild.me).send_messages:
                channel = None
        if channel is None:
            ch = guild.system_channel
            if ch and ch.permissions_for(guild.me).send_messages:
                channel = ch
        if channel is None:
            for ch in guild.text_channels:
                perms = ch.permissions_for(guild.me)
                if perms.view_channel and perms.send_messages:
                    channel = ch
                    break
        if channel is None:
            return  # nowhere safe to speak

        # compose a simple welcome
        try:
            pref = get_cached_prefix(guild.id) if "get_cached_prefix" in globals() else "bc!"
            await channel.send(
                f"👋 Welcome {member.mention}! Glad to have you in **{guild.name}**.\n"
                f"Try `{pref}help` to see what I can do."
            )
        except Exception:
            logging.exception("Failed to send welcome message")
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # keep your existing spawn logic
        from config import settings
        if settings.IS_DEV:
            if guild.id in settings.TEST_GUILDS:
                start_guild_spawn_task(self.bot, guild.id)
        else:
            if guild.id not in settings.TEST_GUILDS:
                start_guild_spawn_task(self.bot, guild.id)

        # try to read preferred announce channel (if your table already has a row)
        row = None
        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT announce_channel_id FROM guild_settings WHERE guild_id=$1",
                    guild.id
                )
        except Exception:
            pass

        # choose where to speak: announce_channel_id → system_channel → first usable text channel
        channel = None
        if row and row["announce_channel_id"]:
            ch = guild.get_channel(row["announce_channel_id"])
            if ch and ch.permissions_for(guild.me).send_messages:
                channel = ch
        if channel is None:
            ch = guild.system_channel
            if ch and ch.permissions_for(guild.me).send_messages:
                channel = ch
        if channel is None:
            for ch in guild.text_channels:
                perms = ch.permissions_for(guild.me)
                if perms.view_channel and perms.send_messages:
                    channel = ch
                    break

        # prefix (fallback to 'bc!' if cache/helper isn't available yet)
        try:
            pref = get_cached_prefix(guild.id)
        except Exception:
            pref = "bc!"
        bot_mention = self.bot.user.mention
        # build the welcome embed
        embed = discord.Embed(
            title=f"Thanks for inviting {self.bot.user.name}! 🎉",
            description=(
                f"**First step:** run `{bot_mention}setup`.\n"
                f"This sets which channels I use for spawns, logs, and announcements."
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="Useful commands",
            value=(
                f"• `{bot_mention}help` — see everything I can do\n"
                f"• `{bot_mention}achievements` — your progress & badges\n"
                f"• `{bot_mention}credits` — attributions & licensing"
            ),
            inline=False
        )
        embed.set_footer(text=f"Prefix here is `{pref}`.")

        # send it (or DM the owner if we can't speak anywhere)
        try:
            if channel:
                await channel.send(embed=embed)
            else:
                if guild.owner and guild.owner.dm_channel is None:
                    await guild.owner.create_dm()
                if guild.owner:
                    await guild.owner.dm_channel.send(embed=embed)
        except Exception:
            # don't crash if we can't send a message
            pass
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.guild is None:
            return await message.channel.send("This is a dm")
        guild_id = message.guild.id
        # auto–eye-roll on every message from that specific user
        # inside on_message, after you computed guild_id
        async with self.bot.db_pool.acquire() as conn:
            react_ids = await conn.fetchval(
                "SELECT react_channel_ids FROM guild_settings WHERE guild_id=$1",
                guild_id
            )
        react_ids = react_ids or []

        if message.channel.id in react_ids:
            if message.author.id == 1381277906017189898:
                try: await message.add_reaction("🙄")
                except Exception: pass
            elif message.author.id == 1376308591115501618:
                try: await message.add_reaction("🐈")
                except Exception: pass
            txt = (message.content or "").casefold()
            if "been" in txt:
                try:
                    await message.add_reaction("👀")
                except Exception:
                    pass             
        if message.author.bot:
            return

        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO accountinfo (discord_id,guild_id)
                VALUES ($1,$2)
                ON CONFLICT (discord_id,guild_id) DO NOTHING;
                """,
                message.author.id,guild_id
            )
            user_id = message.author.id
            bucket = chat_xp_cd.get_bucket(message)
            can_gain = bucket.update_rate_limit() is None
            if can_gain:
                await gain_exp(conn,self.bot,user_id,1,None,guild_id)
        # 0) Try to capture any active spawn in this channel
        name = message.content.strip().lower().replace(" ", "")
        now = datetime.now(timezone.utc)
        async with self.bot.db_pool.acquire() as conn:
            # find the oldest not-yet-expired spawn in this channel
            spawn = await conn.fetchrow(
                """
                SELECT spawn_id, mob_name
                FROM active_spawns
                WHERE channel_id = $1
                AND expires_at > $2
                ORDER BY spawn_time
                LIMIT 1
                """,
                message.channel.id, now
            )
            if spawn and name == spawn["mob_name"].lower().replace(" ", ""):
                # Got it first!
                await achievements.try_grant(self.bot.db_pool,None, user_id, "mob_catch")
                spawn_id = spawn["spawn_id"]
                mob_name = spawn["mob_name"]
                is_golden = (random.randint(1, 20) == 1)
                sac = False
                if MOBS[mob_name]["rarity"]  == 4:
                    await achievements.try_grant(self.bot.db_pool, None, user_id, "epic_mob")
                # 1) Add to the barn (or sacrifice if full)
                #    First ensure the player/barn rows exist:
                await ensure_player(conn,message.author.id,guild_id)
                await barn.ensure_player_and_barn(conn,message.author.id,guild_id)
                await lb_inc(conn,"mobs_caught",message.author.id,guild_id,+1)
                await conn.execute(
                    "INSERT INTO barn_upgrades (user_id,guild_id) VALUES ($1,$2) ON CONFLICT DO NOTHING;",
                    message.author.id,guild_id
                )
                # count current barn occupancy
                occ = await conn.fetchval(
                    "SELECT COALESCE(SUM(count),0) FROM barn WHERE user_id = $1 AND guild_id = $2",
                    message.author.id,guild_id
                )
                size = await conn.fetchval(
                    "SELECT barn_size FROM new_players_guild  WHERE user_id = $1 AND guild_id = $2",
                    message.author.id,guild_id
                )
                    
                if MOBS[mob_name]["hostile"]:
                    sac = True
                    reward = await sucsac(message.channel,message.author,mob_name,is_golden,"because it can't be captured",conn)
                    note = f"this mob is not catchable so it was sacrificed for {reward} emeralds"
                elif occ >= size:
                    sac = True
                    reward = await sucsac(message.channel,message.author,mob_name,is_golden,"because the barn was too full",conn)
                    note = f"sacrificed for {reward} emeralds (barn is full)."
                    
                else:

                    # insert into barn with the golden flag
                    await conn.execute(
                        """
                INSERT INTO barn (user_id, guild_id, mob_name, is_golden, count)
                VALUES ($1, $4, $2, $3, 1)
                ON CONFLICT (user_id, guild_id, mob_name, is_golden)
                DO UPDATE SET count = barn.count + 1
                        """,
                        message.author.id, mob_name, is_golden, guild_id
                    )

                    note = f"placed in your barn ({occ+1}/{size})."
                # 2) Delete the spawn so no one else can catch it
                await conn.execute(
                    "DELETE FROM active_spawns WHERE spawn_id = $1",
                    spawn_id
                )

                # look up rarity info
                rarity = MOBS[mob_name]["rarity"]
                rar_info = RARITIES[rarity]
                color    = COLOR_MAP[rar_info["colour"]]
                if not sac:
                    # build and send the embed
                    embed = discord.Embed(
                        title=f"🏆 {message.author.display_name} caught a {'✨ Golden ' if is_golden else ''} {RARITIES[rarity]['name']} {mob_name}!",
                        description=f"{note}",
                        color=color
                    )
                    embed.add_field(
                        name="Rarity",
                        value=rar_info["name"].title(),
                        inline=True
                    )
                    await message.channel.send(embed=embed)
                    # skip further processing (so they don’t also run a command)
                return

async def setup(bot):
    await bot.add_cog(Events(bot))
