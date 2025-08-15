# cogs/help.py
# A single-file, modern help command with categories, buttons, and a dropdown.
import asyncio
from typing import List, Optional, Tuple

import discord
from discord.ext import commands

# -------- Centralized help metadata --------
# Put ALL your help copy here. Keys can be the command's .name or .qualified_name.
HELP_TEXTS = {
    ########## ADMIN ###############
    "setupbot": {
    "desc": "An easy way to set up the bot (prefix, channels etc.)",
    "usage": "setupbot",
    "aliases": ["setup"],
    },
    "enablewelcome": {
    "desc": "Enables the welcome message for every new server user (inclused @)",
    "usage": "enablewelcome",
    "aliases": ["welcomeon"],
    },
    "disablewelcome": {
    "desc": "Disables the welcome message for every new server user (inclused @)",
    "usage": "disablewelcome",
    "aliases": ["welcomeoff"],
    },
    "setprefix": {
    "desc": "Sets a custom prefix to run commands on the bot for this server",
    "usage": "setprefix [prefix]",
    "aliases": [],
    },
    "levelannounce": {
    "desc": "Sets whether it is announced when someone levels up",
    "usage": "levelannounce [on/off]",
    "aliases": ["levelsannounce","togglelevels"],
    },
    "setlogs": {
    "desc": "Sets a channel for the bot to send any important logs",
    "usage": "levelannounce [on/off]",
    "aliases": ["setlog", "logs"],
    },

    "addgamechannel": {
        "desc": "Add a channel where game commands may be used",
        "usage": "addgamechannel <#channel>",
        "aliases": ["addgame", "addgamech"],
    },
    "removegamechannel": {
        "desc": "Remove a channel where game commands may be used",
        "usage": "removegamechannel <#channel>",
        "aliases": ["removegame", "delgame"],
    },    
    "gamechannels": {
        "desc": "Check the channels where game commands can be used",
        "usage": "gamechannels",
        "aliases": ["listgames"],
    },


    "addlinkchannel": {
        "desc": "Add a channel where the bot may post links",
        "usage": "addlinkchannel <#channel>",
        "aliases": ["addlink", "addlinkch"],
    },
    "removelinkchannel": {
        "desc": "Remove a channel where the bot may post links",
        "usage": "removelinkchannel <#channel>",
        "aliases": ["removelink", "dellink"],
    },    
    "linkchannels": {
        "desc": "Check the channels where the bot may post links",
        "usage": "gamechannels",
        "aliases": ["listlinks"],
    },


    "addspawnchannel": {
        "desc": "Add a channel where mobs can spawn",
        "usage": "addspawnchannel <#channel>",
        "aliases": ["addspawn", "addspawnhannel"],
    },
    "removespawnchannel": {
        "desc": "Remove a channel where mobs can spawn",
        "usage": "removespawnchannel <#channel>",
        "aliases": ["removespawn", "delspawn"],
    },


    "addmilestone": {
        "desc": "Adds a role to give a user when they reach a certain level",
        "usage": "addmilestone <level> <@role>",
        "aliases": [],
    },
    "removemilestone": {
        "desc": "Removes a role to give a user when they reach a certain level",
        "usage": "removemilestone <level>",
        "aliases": [],
    },


    "addreactchannel": {
        "desc": "Add a channel in which the bot can react in",
        "usage": "addreactchannel <#channel>",
        "aliases": ["addreact", "addreactch"],
    },
    "removereactchannel": {
        "desc": "Remove a channel in which the bot can react in",
        "usage": "removereactchannel <#channel>",
        "aliases": ["removereact", "delreact"],
    },
    "reactchannels": {
        "desc": "Check which channels the bot can react in",
        "usage": "removereactchannel <#channel>",
        "aliases": ["listreact"],
    },
    ###################### GAME #######################
    "achievements": {
        "desc": "View someones achievement menu",
        "usage": "achievements <@user>",
        "aliases": ["ach","achs"],
    },    
    "craft": {
        "desc": "Craft an item",
        "usage": "craft [tier] [tool]",
        "aliases": [],
    },    
    "recipe": {
        "desc": "Show the cost of crafting an item",
        "usage": "recipe [tier] [tool]",
        "aliases": [],
    },    
    "shop": {
        "desc": "Display items available to buy, their cost and the ID",
        "usage": "shop",
        "aliases": [],
    },    
    "buy": {
        "desc": "Purchase an item from the shop",
        "usage": "buy [ID/item name]",
        "aliases": [],
    },
    "use": {
        "desc": "Use an item",
        "usage": "use [item name]",
        "aliases": [],
    },
    "sacrifice": {
        "desc": "Sacrifice a mob from your barn",
        "usage": "sacrifice [mob]",
        "aliases": ["sac", "kill"],
    },
    "inv": {
        "desc": "View someones inventory",
        "usage": "inv <@user>",
        "aliases": ["inventory"],
    },
    "give": {
        "desc": "Give another player a mob from your barn",
        "usage": "give <@user> [mob]",
        "aliases": [],
    },
    "breed": {
        "desc": "Breed a mob you have 2 of in the barn",
        "usage": "breed [mob]",
        "aliases": [],
    },
    "bestiary": {
        "desc": "View all the mobs a user has sacrificed",
        "usage": "bestiary <@user>",
        "aliases": ["bs", "bes"],
    },
    "barn": {
        "desc": "View all the mobs a user has in their barn",
        "usage": "barn <@user>",
        "aliases": [],
    },
    "upbarn": {
        "desc": "Upgrades your barn to fit another mob in it, costs wood",
        "usage": "upbarn",
        "aliases": [],
    },
    "chop": {
        "desc": "Chops wood",
        "usage": "chop",
        "aliases": [],
    },
    "mine": {
        "desc": "Mines a random ore based on your pickaxe",
        "usage": "mine",
        "aliases": [],
    },
    "farm": {
        "desc": "Farms a random amount of wheat based on your hoe",
        "usage": "farm",
        "aliases": [],
    },
    "fish": {
        "desc": "Fish a fish using a fishing rod",
        "usage": "fish",
        "aliases": [],
    },
    "aquarium": {
        "desc": "view someones caught fish",
        "usage": "aquarium <@user>",
        "aliases": ["aq"],
    },
    "stronghold": {
        "desc": "play the stronghold minigame",
        "usage": "stronghold",
        "aliases": [],
    },
    ################## GENERAL #####################
    "credits": {
        "desc": "Show Attribution & Licensing of the bot",
        "usage": "credits",
        "aliases": ["license", "licence", "about"],
    },
    "yt": {
        "desc": "Show a link to someones youtube channel (currently not working)",
        "usage": "yt <@user>",
        "aliases": [],
    },
    "linkyt": {
        "desc": "Link your discord account with your youtube channel (dont worry, you wont need to give your password)",
        "usage": "linkyt [channel display name e.g.Beenn]",
        "aliases": [],
    },
    #################### LEADERBOARDS ###################
    "lb": {
        "desc": "Show a menu of different leaderboards",
        "usage": "linkyt [channel display name e.g.Beenn]",
        "aliases": ["leaderboard"],
    },
    "exp": {
        "desc": "Display someones exp profile",
        "usage": "exp <@user>",
        "aliases": ["experience", "level", "lvl","rank"],
    },
    ###################### BG ##########################
    "bg buy": {
        "desc": "Show the possible backgrounds to buy",
        "usage": "bg buy",
        "aliases": [],
    },
    "bg claim": {
        "desc": "Claim all of your purchased backgrounds",
        "usage": "bg claim",
        "aliases": [],
    },
    "bg set": {
        "desc": "Set the background for your exp profile",
        "usage": "bg set [background name]",
        "aliases": [],
    },    
}


HELP_CATEGORIES = {
    # ---------- Admin / Setup ----------
    "setupbot": "Admin",
    "enablewelcome": "Admin",
    "disablewelcome": "Admin",
    "setprefix": "Admin",
    "levelannounce": "Admin",
    "setlogs": "Admin",
    "addgamechannel": "Admin",
    "removegamechannel": "Admin",
    "gamechannels": "Admin",
    "addlinkchannel": "Admin",
    "removelinkchannel": "Admin",
    "linkchannels": "Admin",
    "addspawnchannel": "Admin",
    "removespawnchannel": "Admin",
    "addmilestone": "Admin",
    "removemilestone": "Admin",
    "addreactchannel": "Admin",
    "removereactchannel": "Admin",
    "reactchannels": "Admin",

    # ---------- Game (Core gameplay & items) ----------
    "achievements": "Game",
    "craft": "Game",
    "recipe": "Game",
    "shop": "Game",
    "buy": "Game",
    "use": "Game",
    "sacrifice": "Game",
    "inv": "Game",
    "give": "Game",
    "breed": "Game",
    "bestiary": "Game",
    "barn": "Game",
    "upbarn": "Game",
    "chop": "Game",
    "mine": "Game",
    "farm": "Game",
    "fish": "Game",
    "aquarium": "Game",
    "stronghold": "Game",

    # ---------- Profile & Cosmetics (Backgrounds) ----------
    "bg buy": "Profile & Cosmetics",
    "bg claim": "Profile & Cosmetics",
    "bg set": "Profile & Cosmetics",

    # ---------- Leaderboards & Progress ----------
    "lb": "Leaderboards",
    "exp": "Leaderboards",

    # ---------- General / Utilities ----------
    "credits": "General",
    "yt": "General",
    "linkyt": "General",
}

CATEGORY_ORDER = ["Game", "Admin", "Leaderboards", "General", "Other"]

DISCORD_FIELD_LIMIT = 1024
DISCORD_MESSAGE_LIMIT = 2000

def _chunk_lines_for_field(lines, limit=DISCORD_FIELD_LIMIT):
    """Yield chunks of lines whose joined length <= limit."""
    chunk, length = [], 0
    for line in lines:
        add = len(line) + (1 if chunk else 0)  # + newline if not first
        if length + add > limit:
            if chunk:
                yield "\n".join(chunk)
            # line might itself be long; truncate as last resort
            if len(line) > limit:
                yield line[:limit - 3] + "..."
                chunk, length = [], 0
            else:
                chunk, length = [line], len(line)
        else:
            chunk.append(line)
            length += add
    if chunk:
        yield "\n".join(chunk)

async def _safe_send_long(ctx, lines):
    """Send a long plaintext list safely in <=2000-char chunks."""
    buf = ""
    for line in lines:
        add = ("" if not buf else "\n") + line
        if len(buf) + len(add) > DISCORD_MESSAGE_LIMIT:
            await ctx.send(buf)
            buf = line
        else:
            buf += add
    if buf:
        await ctx.send(buf)

def _meta_for(cmd: commands.Command) -> dict:
    # Try both the short name and the qualified name for groups/subcommands
    return HELP_TEXTS.get(cmd.name) or HELP_TEXTS.get(cmd.qualified_name, {}) or {}

def command_signature(cmd: commands.Command) -> str:
    """Build a readable signature like: ban <member> [reason...]"""
    name = cmd.qualified_name
    params = []
    for name_, param in cmd.clean_params.items():
        if param.kind == param.VAR_POSITIONAL:
            params.append(f"[{name_}...]")
        elif param.default is not param.empty:
            params.append(f"[{name_}]")
        else:
            params.append(f"<{name_}>")
    return f"{name} " + " ".join(params) if params else name

def human_perms(perms: discord.Permissions) -> List[str]:
    return [p.replace("_", " ").title() for p, v in perms if v]

def get_cooldown(cmd: commands.Command) -> Optional[str]:
    cd = getattr(cmd, "cooldown", None)
    if not cd:
        return None
    return f"{cd.rate} use(s) per {int(cd.per)}s"

def is_owner_only(cmd: commands.Command) -> bool:
    checks = getattr(cmd, "checks", [])
    for chk in checks:
        if getattr(chk, "__qualname__", "").endswith("is_owner.<locals>.predicate"):
            return True
    return False

# -------- Embed builders --------

def make_command_embed(ctx: commands.Context, cmd: commands.Command) -> discord.Embed:
    prefix = ctx.clean_prefix
    meta = _meta_for(cmd)

    # Centralized description & usage
    description = (meta.get("desc") or cmd.help or "No description provided.").strip()
    usage = meta.get("usage")
    display_aliases = meta.get("aliases", cmd.aliases)

    e = discord.Embed(
        title=f"{prefix}{command_signature(cmd)}",
        description=description,
        color=discord.Color.blurple(),
    )

    if usage:
        e.add_field(name="Usage", value=f"`{prefix}{usage}`", inline=False)

    if display_aliases:
        e.add_field(name="Aliases", value=", ".join(f"`{a}`" for a in display_aliases), inline=False)

    cd = get_cooldown(cmd)
    if cd:
        e.add_field(name="Cooldown", value=cd, inline=True)

    # If you annotate commands with .requires (discord.ext.commands.flags), show bot perms
    if getattr(cmd, "requires", None) and cmd.requires.guild and cmd.requires.permissions:
        e.add_field(
            name="Bot Needs",
            value=", ".join(p.replace("_", " ").title() for p in cmd.requires.permissions),
            inline=True,
        )

    if is_owner_only(cmd):
        e.add_field(name="Access", value="Owner only", inline=True)

    e.set_footer(text=f"Use {prefix}help {cmd.qualified_name} for subcommands (if any).")
    return e

def make_category_embeds(
    ctx: commands.Context,
    title: str,
    pairs: List[Tuple[str, List[commands.Command]]],
) -> List[discord.Embed]:
    """Build one embed per category (Cog or custom), splitting long command lists across fields."""
    prefix = ctx.clean_prefix
    embeds: List[discord.Embed] = []

    for category_name, cmds in pairs:
        if not cmds:
            continue

        e = discord.Embed(
            title=title,
            description=f"**Category:** {category_name}",
            color=discord.Color.blurple(),
        )

        # Build lines first
        lines = []
        for c in cmds:
            meta = _meta_for(c)
            desc = (meta.get("desc") or c.short_doc or c.help or "No description").strip()
            usage = meta.get("usage")  # prefer centralized usage
            if usage:
                lines.append(f"`{prefix}{usage}` — {desc}")
            else:
                lines.append(f"`{prefix}{command_signature(c)}` — {desc}")

        # Split into multiple fields of ≤1024 chars
        chunks = list(_chunk_lines_for_field(lines, DISCORD_FIELD_LIMIT))
        if not chunks:
            chunks = ["No commands available."]

        e.add_field(name="Commands", value=chunks[0], inline=False)
        for chunk in chunks[1:]:
            e.add_field(name="Commands (cont.)", value=chunk, inline=False)

        e.set_footer(text=f"Use {prefix}help <command> for details. • {len(cmds)} command(s)")
        embeds.append(e)

    if not embeds:
        embeds.append(discord.Embed(title=title, description="No commands available.", color=discord.Color.blurple()))
    return embeds

# -------- Views (Buttons + Dropdown) --------

class Paginator(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed], author_id: int, options: Optional[List[discord.SelectOption]] = None):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.index = 0
        self.author_id = author_id
        if options:
            self.add_item(CategorySelect(options, self))

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.author_id

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

class CategorySelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption], pager: Paginator):
        super().__init__(placeholder="Jump to category…", min_values=1, max_values=1, options=options)
        self.pager = pager

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        for i, emb in enumerate(self.pager.embeds):
            if emb.description and chosen in emb.description:
                self.pager.index = i
                break
        await interaction.response.edit_message(embed=self.pager.embeds[self.pager.index], view=self.pager)

# -------- The Cog & HelpCommand --------

class PrettyHelp(commands.HelpCommand):
    """Custom help that supports: help, help <command>, help <category>."""

    def __init__(self):
        super().__init__(command_attrs={"help": "Show help for commands and categories."})

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        # Group visible commands by Cog
        pairs: List[Tuple[str, List[commands.Command]]] = []
        # Group commands by our custom category names
        category_map = {}
        for cog, cmds in mapping.items():
            for cmd in cmds:
                if cmd.hidden:
                    continue
                try:
                    if not await cmd.can_run(ctx):
                        continue
                except Exception:
                    pass
                # Look up category from mapping
                cat_name = HELP_CATEGORIES.get(cmd.qualified_name) or HELP_CATEGORIES.get(cmd.name) or "Other"
                category_map.setdefault(cat_name, []).append(cmd)

        # Sort categories and commands
        pairs = []
        for cat_name, cmds in sorted(category_map.items(), key=lambda x: x[0].lower()):
            cmds.sort(key=lambda c: c.qualified_name)
            pairs.append((cat_name, cmds))
        pairs.sort(key=lambda x: CATEGORY_ORDER.index(x[0]) if x[0] in CATEGORY_ORDER else len(CATEGORY_ORDER))    
        embeds = make_category_embeds(ctx, f"{bot.user.name} Help", pairs)
        options = [discord.SelectOption(label=cog_name, description=f"{len(cmds)} command(s)") for cog_name, cmds in pairs]
        view = Paginator(embeds, author_id=ctx.author.id, options=options)

        try:
            await ctx.send(embed=embeds[0], view=view)
        except discord.HTTPException:
            lines = []
            for cat_name, cmds in pairs:
                lines.append(f"**{cat_name}**")
                for c in cmds:
                    meta = _meta_for(c)
                    desc = meta.get("desc") or c.short_doc or c.help or "No description"
                    usage = meta.get("usage") or command_signature(c)
                    lines.append(f"- {ctx.clean_prefix}{usage} — {desc}")
                lines.append("")  # blank line between categories
            await _safe_send_long(ctx, lines)

    async def send_cog_help(self, cog):
        ctx = self.context
        cmds = [c for c in cog.get_commands() if not c.hidden]
        cmds.sort(key=lambda x: x.qualified_name)
        embeds = make_category_embeds(ctx, f"{cog.qualified_name} Help", [(cog.qualified_name, cmds)])
        await ctx.send(embed=embeds[0])

    async def send_command_help(self, command):
        ctx = self.context
        await ctx.send(embed=make_command_embed(ctx, command))

    async def send_group_help(self, group: commands.Group):
        ctx = self.context
        base = make_command_embed(ctx, group)
        subs = [c for c in group.commands if not c.hidden]
        subs.sort(key=lambda x: x.qualified_name)
        if subs:
            lines = []
            for c in subs:
                meta = _meta_for(c)
                desc = meta.get("desc") or c.short_doc or c.help or "No description"
                usage = meta.get("usage") or command_signature(c)
                lines.append(f"`{ctx.clean_prefix}{usage}` — {desc}")
            base.add_field(name="Subcommands", value="\n".join(lines[:1024]), inline=False)
        await ctx.send(embed=base)

class HelpCog(commands.Cog):
    """Registers PrettyHelp and offers an owner command to DM the full list."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._old_help = bot.help_command
        bot.help_command = PrettyHelp()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._old_help

    @commands.is_owner()
    @commands.command(name="dmhelp", help="DM yourself the full help index.")
    async def dm_help(self, ctx: commands.Context):
        dest = await ctx.author.create_dm()

        class DMHelp(PrettyHelp):
            async def get_destination(self):
                return dest

        old = self.bot.help_command
        self.bot.help_command = DMHelp()
        self.bot.help_command.cog = self
        try:
            # Ask the help system to regenerate the full index in DMs
            await self.bot.help_command.send_bot_help(self.bot.cogs_to_commands_mapping() if hasattr(self.bot, "cogs_to_commands_mapping") else self.bot.cogs)
        except Exception:
            await dest.send(f"Use `{ctx.clean_prefix}help` in a server — I couldn't DM the rich version.")
        finally:
            self.bot.help_command = old
            self.bot.help_command.cog = self

# -------- Extension entry point --------

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
