from discord.ext import commands
import discord
from services import crafting, shop, activities, fishing, barn, progression, yt_link
from services.monetization import has_premium,peek_premium
from utils.prefixes import get_cached_prefix
from constants import BLOCKED_SHOP_ITEMS
import os
INVITE_URL = "https://discord.com/oauth2/authorize?client_id=1396168326132011119&scope=bot%20applications.commands&permissions=3816884137024"

class General(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
    @commands.command(name="linkyt")
    async def linkyt(self,ctx, *, channel_name: str):
        await yt_link.linkyt(self.bot.db_pool,ctx,channel_name)

    @commands.command(name="yt")
    async def yt(self, ctx, *, who = None):
        await yt_link.yt(self.bot.db_pool,ctx, who)
    @commands.command(name="credits", aliases=["license", "licence", "about"])
    async def credits(self,ctx):
        pref = get_cached_prefix(ctx.guild.id if ctx.guild else None)

        e = discord.Embed(
            title="Attribution & Licensing",
            description=(
                "This bot **does not use any images from community wikis**.\n\n"
                "Media used by the bot falls into these categories:\n"
                "• **Original assets** created for the bot.\n"
                "• **User-submitted content** used with permission.\n"
                "• **Mojang-owned material** (e.g., screenshots/textures) only where permitted by the "
                "**Minecraft Usage Guidelines** and with the required disclaimer."
            ),
            color=discord.Color.blurple()
        )

        e.add_field(
            name="Trademark / Affiliation",
            value=(
                "NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT."
            ),
            inline=False
        )

        e.add_field(
            name="Learn more",
            value=(
                "• Minecraft Usage Guidelines (covers when/how Mojang content may be used).\n"
            ),
            inline=False
        )

        e.set_footer(text="Questions about a specific image? Use the source command above.")
        await ctx.send(embed=e)

    @commands.command(name="invite", help="Get the bot's invite link.")

    async def invite(self, ctx: commands.Context):
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Invite me", url=INVITE_URL))
        await ctx.send(f"Add me to your server with this link:\n<{INVITE_URL}>", view=view)

    @commands.command(name="discord", help="The invite to the bot's discord server.")
    async def disc(self, ctx: commands.Context):
        await ctx.send(f"Join the discord! -> https://discord.gg/7NrMN4mdgA")


    @commands.command(name="premium")
    async def premium(self, ctx: commands.Context):
        PREMIUM_SKU_ID = "1405934572436193462"
        APPLICATION_ID = os.getenv("APPLICATION_ID")
        """Send a button linking to the Premium SKU in the app store."""
        if not APPLICATION_ID:
            return await ctx.send("⚠️ APPLICATION_ID environment variable is not set.")

        store_url = f"https://discord.com/application-directory/{APPLICATION_ID}/store/{PREMIUM_SKU_ID}"

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="Unlock Premium",
            style=discord.ButtonStyle.link,
            url=store_url
        ))

        embed = discord.Embed(
            title="✨ Premium",
            description="Get extra perks and shorter cooldowns with Premium.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed, view=view)
    @commands.command(name="mypremium")
    async def my_premium(self, ctx):
        # Async DB/API check (authoritative)
        db_check = await has_premium(self.bot.db_pool, ctx.author.id)

        # Sync cache peek (what your cooldown decorators use)
        cache_check = peek_premium(ctx.author.id)

        await ctx.send(
            f"**Premium check for {ctx.author}:**\n"
            f"- DB says: `{db_check}`\n"
            f"- Cache peek says: `{cache_check}`"
        )


async def setup(bot):
    await bot.add_cog(General(bot))