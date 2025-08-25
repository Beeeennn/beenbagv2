# cogs/link_comments_api.py
import asyncio
import re
from typing import Dict, Optional
import aiohttp, asyncpg
from contextlib import suppress
import discord

CODE_RE = re.compile(r"\b([A-Z0-9]{8})\b")
API_BASE = "https://www.googleapis.com/youtube/v3/commentThreads"

# ---------- DB helpers ----------
async def _fetch_pending_links(pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT discord_id, guild_id, yt_channel_id, code, expires_at
              FROM pending_links
             WHERE expires_at > NOW()
            """
        )

async def _complete_link(pool, guild_id: int, discord_id: int,
                         yt_channel_id: str, yt_channel_name: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO accountinfo (guild_id, discord_id, yt_channel_id, yt_channel_name)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (guild_id, discord_id) DO UPDATE
              SET yt_channel_id = EXCLUDED.yt_channel_id,
                  yt_channel_name = EXCLUDED.yt_channel_name
            """,
            guild_id, discord_id, yt_channel_id, yt_channel_name
        )
        await conn.execute(
            "DELETE FROM pending_links WHERE guild_id = $1 AND discord_id = $2",
            guild_id, discord_id
        )

# ---------- API calls ----------
async def _fetch_newest_comments(session: aiohttp.ClientSession, api_key: str, video_id: str, max_results: int):
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "time",
        "maxResults": str(max_results),
        "key": api_key,
    }
    async with session.get(API_BASE, params=params, timeout=15) as r:
        r.raise_for_status()
        data = await r.json()
    return data.get("items", [])

def _parse_comment(item: dict):
    try:
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        comment_id = item["snippet"]["topLevelComment"]["id"]
        text = snippet.get("textDisplay") or snippet.get("textOriginal") or ""
        author_name = snippet.get("authorDisplayName") or "YouTube User"
        author_cid = (snippet.get("authorChannelId") or {}).get("value", "")
        published_at = snippet.get("publishedAt") or ""
        return comment_id, text, author_cid, author_name, published_at
    except Exception:
        return None, "", "", "", ""

class GlobalCommentPoller:
    """
    Polls ONE verification video for ALL guilds.
    Matches 8-char codes against pending_links and links the YT author channel.
    """
    def __init__(self, bot: discord.Client, pool, api_key: str, video_id: str,
                 poll_seconds: int = 120, max_results: int = 100):
        self.bot = bot
        self.pool = pool
        self.api_key = api_key
        self.video_id = video_id
        self.poll_seconds = poll_seconds
        self.max_results = max_results
        self._task: Optional[asyncio.Task] = None
        self._alive = False
        self._seen: set[str] = set()

    async def start(self):
        if self._alive:
            return
        self._alive = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._alive = False
        if self._task:
            with suppress(Exception):
                await asyncio.wait_for(self._task, timeout=2)

    async def _run(self):
        await self.bot.wait_until_ready()
        async with aiohttp.ClientSession() as session:
            while self._alive and not self.bot.is_closed():
                try:
                    items = await _fetch_newest_comments(
                        session, self.api_key, self.video_id, self.max_results
                    )
                    if not items:
                        await asyncio.sleep(self.poll_seconds); continue

                    pending = await _fetch_pending_links(self.pool)
                    pending_by_code: Dict[str, asyncpg.Record] = {p["code"]: p for p in pending}
                    if not pending_by_code:
                        await asyncio.sleep(self.poll_seconds); continue

                    # oldest -> newest
                    for it in reversed(items):
                        comment_id, text, author_cid, author_name, _ts = _parse_comment(it)
                        if not comment_id or comment_id in self._seen:
                            continue

                        m = CODE_RE.search((text or "").upper())
                        if not m:
                            self._seen.add(comment_id); continue

                        code = m.group(1)
                        pending_row = pending_by_code.get(code)
                        if not pending_row:
                            self._seen.add(comment_id); continue

                        await _complete_link(
                            self.pool,
                            pending_row["guild_id"],
                            pending_row["discord_id"],
                            author_cid or "",
                            author_name or "YouTube User",
                        )

                        user = self.bot.get_user(pending_row["discord_id"])
                        if user:
                            with suppress(Exception):
                                # in cogs/link_comments_api.py, inside GlobalCommentPoller when a code matches:
                                content = (
                                    f"✅ Linked your YouTube channel **{author_name}**."
                                    + (f" (ID: {author_cid})" if author_cid else "")
                                )
                                # queue it — this returns immediately; the outbox will pace sends
                                await self.bot.outbox.dm(pending_row["discord_id"], content)

                        self._seen.add(comment_id)
                        pending_by_code.pop(code, None)

                    await asyncio.sleep(self.poll_seconds)
                except Exception:
                    await asyncio.sleep(self.poll_seconds)

# public entrypoint
_global_poller: Optional[GlobalCommentPoller] = None

def setup_comment_link_listener_api(bot, pool, api_key: str, video_id: str, poll_seconds: int = 120):
    """
    Call once at startup, after db pool is ready:
        setup_comment_link_listener_api(self, self.db_pool, settings.YT_API_KEY, settings.YT_VERIFY_VIDEO_ID)
    """
    global _global_poller
    if _global_poller is None:
        _global_poller = GlobalCommentPoller(bot, pool, api_key, video_id, poll_seconds=poll_seconds)
        bot.loop.create_task(_global_poller.start())
