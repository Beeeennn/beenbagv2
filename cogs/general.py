from discord.ext import commands
import discord
from services import crafting, shop, activities, fishing, barn, progression, yt_link
from utils.prefixes import get_cached_prefix
from constants import BLOCKED_SHOP_ITEMS

INVITE_URL = "https://discord.com/oauth2/authorize?client_id=1396168326132011119&scope=bot%20applications.commands&permissions=2714688679152"

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
    
async def setup(bot):
    await bot.add_cog(General(bot))