# core/checks.py
from discord.ext import commands
from utils.permissions import is_guild_admin
from utils.permissions import bot_can_send, bot_can_react
import asyncpg

def is_admin():
    """User must be a guild admin (Manage Guild or Administrator)."""
    async def predicate(ctx: commands.Context):
        return ctx.guild is None or is_guild_admin(ctx.author)
    return commands.check(predicate)

def only_in_game_channels():
    """
    Allow commands only in configured game channels for this guild,
    unless none configured, or user is admin.
    """
    async def predicate(ctx: commands.Context):
        if ctx.guild is None:
            return True
        if is_guild_admin(ctx.author):
            return True
        pool: asyncpg.Pool = ctx.bot.db_pool
        async with pool.acquire() as conn:
            ids = await conn.fetchval(
                "SELECT game_channel_ids FROM guild_settings WHERE guild_id=$1",
                ctx.guild.id
            )
        return not ids or (ctx.channel.id in ids)
    return commands.check(predicate)

def require_bot_send():
    """Ensure the bot can send messages in this channel."""
    async def predicate(ctx: commands.Context):
        return bot_can_send(ctx)
    return commands.check(predicate)

def require_bot_react():
    """Ensure the bot can add reactions in this channel."""
    async def predicate(ctx: commands.Context):
        return bot_can_react(ctx)
    return commands.check(predicate)
