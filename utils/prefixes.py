# utils/prefixes.py
from config import settings
import discord
from typing import List
from discord.ext import commands

_prefix_cache: dict[int | None, str] = {}
DEFAULT_PREFIX = settings.DEFAULT_PREFIX

async def warm_prefix_cache(pool):
    rows = await pool.fetch("SELECT guild_id, command_prefix FROM guild_settings")
    for r in rows:
        _prefix_cache[r["guild_id"]] = r["command_prefix"] or DEFAULT_PREFIX

def get_cached_prefix(gid: int | None) -> str:
    if gid is None: return DEFAULT_PREFIX
    return _prefix_cache.get(gid, DEFAULT_PREFIX)

def sanitize_prefix(raw: str | None) -> str | None:
    if not raw: return None
    s = raw.strip()
    if not s or len(s) > 8 or any(ch.isspace() for ch in s): return None
    return s
async def dynamic_prefix(bot, message: discord.Message) -> List[str]:
    """
    Returns a list of valid prefixes for the given guild/message.
    Always includes mention prefixes.
    """
    base_prefix = "!"
    if message.guild:
        base_prefix = get_cached_prefix(message.guild.id)

    return commands.when_mentioned_or(base_prefix)(bot, message)