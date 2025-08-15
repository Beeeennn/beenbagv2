import asyncio
from datetime import timedelta
import discord


async def cycle_presence(bot):
    await bot.wait_until_ready()
    i = 0
    while not bot.is_closed():
        # Recompute dynamic statuses each cycle so guild count stays fresh
        statuses = [
            discord.Game("!help"),
            discord.Activity(type=discord.ActivityType.listening, name="your feedback"),
            discord.Activity(type=discord.ActivityType.watching,  name=f"{len(bot.guilds)} servers"),
        ]
        activity = statuses[i % len(statuses)]
        await bot.change_presence(status=discord.Status.online, activity=activity)
        i += 1
        await asyncio.sleep(600)  # 5 min is safe
        
