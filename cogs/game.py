from discord.ext import commands
from services import crafting, shop, activities, inventory, fishing, barn,exp_display, progression, yt_link, minigames,achievements
from utils.parsing import parse_item_and_qty, _norm_item_from_args
from constants import BLOCKED_SHOP_ITEMS
import discord
from core.decorators import premium_cooldown, premium_only, send_premium_only_message
class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot  # expects bot.db_pool to be set elsewhere


    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure tables + sync registry when the bot boots
        await achievements.ensure_schema(self.bot.db_pool)
        await achievements.sync_master(self.bot.db_pool)
        activity = discord.Activity(type=discord.ActivityType.watching, name="your server")
        await self.bot.change_presence(
            status=discord.Status.online,   # online | idle | dnd | invisible
            activity=activity
        )

    @commands.command(name="achievements", aliases=["ach","achs"])
    async def achievements_cmd(self, ctx, *, who: str | None = None):
        user = ctx.author
        if who and ctx.message.mentions:
            user = ctx.message.mentions[0]
        await achievements.open_achievements_menu(self.bot.db_pool, ctx, user.id)
    # ---------- Crafting ----------
    @commands.command(name="craft")
    @commands.cooldown(1, 1, commands.BucketType.member)
    async def craft_cmd(self, ctx, *args):
        if not args:
            return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}craft <tool> [tier]`")

        # list of valid tier names (lowercase)
        valid_tiers = {"wood", "stone", "iron", "gold", "diamond"}

        args = list(args)
        tier = None
        tool_parts = []

        for arg in args:
            if tier is None and arg.lower() in valid_tiers:
                tier = arg.lower()
            else:
                tool_parts.append(arg)

        tool = "_".join(tool_parts).lower()

        if not tool:
            return await ctx.send("❌ You must specify a tool to craft.")

        await crafting.craft(ctx, self.bot.db_pool, tool, tier)
    @craft_cmd.error
    async def chop_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            return await ctx.send(f"This command is on cooldown. Try again in {retry} second{'s' if retry != 1 else ''}.")
        raise error

    @commands.command(name="recipe")
    async def recipe(self, ctx, *args):
        if not args:
            return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}craft <tool> [tier]`")

        # list of valid tier names (lowercase)
        valid_tiers = {"wood", "stone", "iron", "gold", "diamond"}

        args = list(args)
        tier = None
        tool_parts = []

        for arg in args:
            if tier is None and arg.lower() in valid_tiers:
                tier = arg.lower()
            else:
                tool_parts.append(arg)

        tool = "_".join(tool_parts).lower()

        if not tool:
            return await ctx.send("❌ You must specify a tool to get the recipe of.")

        await crafting.recipe(ctx, self.bot.db_pool, tool, tier)

    @recipe.error
    async def recipe_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}recipe <tool> [tier]`")
        raise error

    # ---------- Shop ----------
    @commands.command(name="shop")
    async def shop_cmd(self, ctx):
        # choose ONE: either shop.show(...) or shop.shop(...)
        # Here assuming services.shop.show(ctx, pool)
        await shop.shop(self.bot.db_pool,ctx)

    @commands.command(name="buy")
    async def buy(self, ctx, *args):
        item_norm = _norm_item_from_args(args)
        if item_norm in BLOCKED_SHOP_ITEMS:
            return await ctx.send("❌ EXP bottles are no longer sold.")
        # services.shop.buy(pool, ctx, args)
        await shop.buy(self.bot.db_pool, ctx, args)

    @commands.command(name="use")
    async def use_cmd(self, ctx, *, args: str = ""):
        try:
            item_name, quantity = parse_item_and_qty(args)
            if quantity <= 0:
                return await ctx.send("❌ Quantity must be at least 1.")
            if item_name == "fish food" and quantity % 100 != 0:
                return await ctx.send("❌ You must use fish food in multiples of 100.")
            # services.shop.use(ctx, pool, bot, item_name, quantity)
            await shop.use(ctx, self.bot.db_pool, self.bot, item_name, quantity)
        except ValueError:
            return await ctx.send(
                f"❌ Use it like `!use <item> [quantity]` — e.g. "
                f"`{ctx.clean_prefix}use exp bottle 5` or `{ctx.clean_prefix}use 5 exp bottle`."
            )

    # ---------- Barn / Mobs ----------
    @commands.command(name="sacrifice", aliases=["sac", "kill"])
    async def sacrifice(self, ctx, *, mob_name: str):
        # services.barn.sac(ctx, pool, mob_name)
        await barn.sac(self.bot.db_pool, ctx, mob_name)

    @commands.command(name="inv", aliases=["inventory"])
    async def inv(self, ctx, *, who: str = None):
        await inventory.inv(self.bot.db_pool,ctx,who)

    @commands.command(name="give")
    async def give(self, ctx, who: str, *, mob: str):
        # services.barn.give(pool, ctx, who, mob)
        await barn.give(self.bot.db_pool, ctx, who, mob)

    @give.error
    async def give_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}give <player> <mob>`")
        raise error

    @commands.command(name="breed")
    @premium_cooldown(5, 86400, commands.BucketType.member) # 5 uses per day
    async def breed(self, ctx, *, mob: str):
        # services.barn.breed(pool, ctx, mob)
        await barn.breed(self.bot.db_pool, ctx, mob)

    @breed.error
    async def breed_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            hrs = retry // 3600
            mins = (retry % 3600) // 60
            parts = []
            if hrs: parts.append(f"{hrs} h")
            if mins: parts.append(f"{mins} m")
            when = " ".join(parts) or f"{retry}s"
            return await ctx.send(f"❌ You’ve used all 5 breeds for today. Try again in {when}.")
        raise error

    @commands.command(name="bestiary", aliases=["bs", "bes"])
    async def bestiary(self, ctx, *, who: str = None):
        # services.barn.bestiary(pool, ctx, who)
        await barn.bestiary(self.bot.db_pool, ctx, who)

    @commands.command(name="barn")
    async def barn_cmd(self, ctx, *, who: str = None):
        # services.barn.barn(pool, ctx, who)
        await barn.barn(self.bot.db_pool, ctx, who)

    @commands.command(name="upbarn")
    async def upbarn(self, ctx):
        # services.barn.upbarn(pool, ctx)
        await barn.upbarn(self.bot.db_pool, ctx)

    # ---------- Activities ----------
    @commands.command(name="chop")
    @premium_cooldown(1, 60, commands.BucketType.member)
    async def chop(self, ctx):
        # services.activities.chop(pool, ctx)
        await activities.chop(self.bot.db_pool, ctx)

    @chop.error
    async def chop_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            return await ctx.send(f"This command is on cooldown. Try again in {retry} second{'s' if retry != 1 else ''}.")
        raise error

    @commands.command(name="mine")
    @premium_cooldown(1, 120, commands.BucketType.member)
    async def mine(self, ctx):
        # services.activities.mine(pool, ctx)
        await activities.mine(self.bot.db_pool, ctx)

    @mine.error
    async def mine_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            return await ctx.send(f"You’re too tired to mine again now! Try again in {retry}s.")
        raise error

    @commands.command(name="farm")
    @premium_cooldown(1, 120, commands.BucketType.member)
    async def farm(self, ctx):
        # services.activities.farm(pool, ctx)
        await activities.farm(self.bot.db_pool, ctx)

    @farm.error
    async def farm_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            return await ctx.send(f"You’re too tired to farm again now! Try again in {retry}s.")
        raise error

    # ---------- Fishing / Aquarium ----------
    @commands.command(name="fish")
    @premium_cooldown(1, 90, commands.BucketType.member)
    async def fish(self, ctx):
        # services.fishing.make_fish(pool, ctx, path)
        await fishing.make_fish(self.bot.db_pool, ctx, "assets/fish/")

    @fish.error
    async def fish_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            return await ctx.send(f"You are too tired to fish again. Try again in {retry} second{'s' if retry != 1 else ''}.")
        raise error

    @commands.command(name="aquarium", aliases=["aq"])
    @premium_cooldown(5, 5, commands.BucketType.member)
    async def aquarium(self, ctx, *, who: str = None):
        # services.fishing.generate_aquarium(pool, ctx, who)
        await fishing.generate_aquarium(self.bot.db_pool, ctx, who)

    @commands.command(name = "missingfish", aliases=["missfish","mfish"])
    @premium_only()
    async def missingfish(self, ctx, who: str | None = None):
        await fishing.missing_fish(self.bot.db_pool,ctx,who)
    @missingfish.error
    async def missing_fish_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            return await send_premium_only_message(ctx)
        raise error
    # ---------- Minigames ----------
    @commands.command(name="stronghold")
    @premium_cooldown(1, 3600, commands.BucketType.member)
    async def stronghold(self, ctx):
        # services.minigames.c_stronghold(pool, ctx)
        await minigames.c_stronghold(self.bot.db_pool, ctx)
    @stronghold.error
    async def stronghold_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            retry = int(error.retry_after)
            return await ctx.send(f"This command is on cooldown. Try again in {retry} second{'s' if retry != 1 else ''}.")
        raise error

async def setup(bot):
    await bot.add_cog(Game(bot))
