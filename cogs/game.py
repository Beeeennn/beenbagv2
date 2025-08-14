from discord.ext import commands
from services import crafting, shop, activities, inventory, fishing, barn, progression, yt_link, minigames,achievements
from utils.parsing import parse_item_and_qty, _norm_item_from_args
from constants import BLOCKED_SHOP_ITEMS

class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot  # expects bot.db_pool to be set elsewhere


    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure tables + sync registry when the bot boots
        await achievements.ensure_schema(self.bot.db_pool)
        await achievements.sync_master(self.bot.db_pool)

    @commands.command(name="achievements", aliases=["achs", "ach"])
    async def achievements_cmd(self, ctx, *, who: str = None):
        user = ctx.author if not who else (ctx.message.mentions[0] if ctx.message.mentions else ctx.author)
        owned, not_owned = await achievements.list_user_achievements(self.bot.db_pool, user.id)

        if not owned and not not_owned:
            return await ctx.send("No achievements defined yet.")

        lines = []
        if owned:
            lines.append(f"🏆 **{user.display_name} — Unlocked ({len(owned)})**")
            for o in owned:
                times = f" ×{o['times_awarded']}" if o.get("repeatable") and o["times_awarded"] > 1 else ""
                lines.append(f"• **{o['name']}**{times} — {o['description']} *(+{o['exp']} EXP)*")
        if not_owned:
            lines.append("")
            lines.append(f"🔒 **Locked ({len(not_owned)})**")
            for n in not_owned:
                lines.append(f"• **{n['name']}** — {n['description']} *(+{n['exp']} EXP)*")

        # Discord has message length limits; chunk if you expect a lot
        await ctx.send("\n".join(lines[:1900]))
    # ---------- Crafting ----------
    @commands.command(name="craft")
    async def craft_cmd(self, ctx, *args):
        if not args:
            return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}craft <tool> [tier]`")
        tool = args[0] if len(args) == 1 else "_".join(args[:-1])
        tier = None if len(args) == 1 else args[-1]
        # services.crafting.craft(ctx, pool, tool, tier)
        await crafting.craft(ctx, self.bot.db_pool, tool, tier)

    @commands.command(name="recipe")
    async def recipe(self, ctx, *args):
        # services.crafting.recipe(ctx, args)
        await crafting.recipe(ctx, args)

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
        await shop.shop(ctx, self.bot.db_pool)

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
    @commands.cooldown(5, 86400, commands.BucketType.user)  # 5 uses per day
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
    @commands.cooldown(1, 60, commands.BucketType.user)
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
    @commands.cooldown(1, 120, commands.BucketType.user)
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
    @commands.cooldown(1, 120, commands.BucketType.user)
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
    @commands.cooldown(1, 90, commands.BucketType.user)
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
    async def aquarium(self, ctx, *, who: str = None):
        # services.fishing.generate_aquarium(pool, ctx, who)
        await fishing.generate_aquarium(self.bot.db_pool, ctx, who)

    # ---------- Minigames ----------
    @commands.command(name="stronghold")
    async def stronghold(self, ctx):
        # services.minigames.c_stronghold(pool, ctx)
        await minigames.c_stronghold(self.bot.db_pool, ctx)


async def setup(bot):
    await bot.add_cog(Game(bot))
