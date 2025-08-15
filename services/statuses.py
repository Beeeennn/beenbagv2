import asyncio
from datetime import timedelta
import discord


async def cycle_presence(bot):
    STATUSES = [
    discord.Game("!help"),
    discord.Activity(type=discord.ActivityType.listening, name="your feedback"),
    discord.Activity(type=discord.ActivityType.watching,  name=f"{len(bot.guilds)} servers"),
    ]

    await bot.wait_until_ready()
    i = 0
    while not bot.is_closed():
        activity = STATUSES[i % len(STATUSES)]
        await bot.change_presence(status=discord.Status.online, activity=activity)
        i += 1
        await asyncio.sleep(300)  # change every 5 minutes (safer)
        
