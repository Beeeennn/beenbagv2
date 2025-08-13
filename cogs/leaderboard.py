from discord.ext import commands
from services import crafting, shop, activities, fishing, barn, progression, yt_link
from utils.parsing import parse_item_and_qty,_norm_item_from_args
from constants import BLOCKED_SHOP_ITEMS
class Leaderboard(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="exp", aliases=["experience", "level", "lvl"])
    async def exp_cmd(self,ctx, *, who: str = None):
        await progression.exp_cmd(self.bot.db_pool,ctx,who)
async def setup(bot):
    await bot.add_cog(Leaderboard(bot))