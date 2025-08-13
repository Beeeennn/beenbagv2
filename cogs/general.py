from discord.ext import commands
from services import crafting, shop, activities, fishing, barn, progression, yt_link
from utils.parsing import parse_item_and_qty,_norm_item_from_args
from constants import BLOCKED_SHOP_ITEMS
class General(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
async def setup(bot):
    await bot.add_cog(General(bot))