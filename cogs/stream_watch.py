# cogs/stream_watch.py
from __future__ import annotations

import asyncio, os, re, json, html, math, time
from typing import Optional, Tuple, Dict

import discord
from discord.ext import commands, tasks
import aiohttp
from urllib.parse import urlparse, parse_qs

# ---------- Config ----------
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
USER_AGENT = "beenbag/streamwatch (+https://discord.com) Mozilla/5.0"

# ---------- YouTube helpers (RSS + no-API LIVE check) ----------

_CH_REGEX = re.compile(
    r"(?:youtube\.com/(?:@(?P<h>[\w\-.]+)|channel/(?P<c>UC[\w-]{21}[AQgw])))|(?P<id>UC[\w-]{21}[AQgw])",
    re.I,
)
_PLAYER_JSON = re.compile(r'ytInitialPlayerResponse\s*=\s*({.*?});', re.S)
_DATA_JSON   = re.compile(r'ytInitialData\s*=\s*({.*?});', re.S)
_VID_IN_URL  = re.compile(r'(?:v=|/)([a-zA-Z0-9_-]{11})(?:\W|$)')

def _extract_channel_token(text: str) -> Optional[str]:
    if not text: return None
    m = _CH_REGEX.search(text)
    return (m.group("c") or m.group("id") or m.group("h")) if m else None

def _rss_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

def _video_id_from_url(url: str) -> Optional[str]:
    try:
        q = parse_qs(urlparse(url).query)
        if "v" in q and q["v"]:
            return q["v"][0]
        m = _VID_IN_URL.search(url)
        return m.group(1) if m else None
    except Exception:
        return None

def _parse_latest_video(xml_text: str) -> Optional[tuple[str, str, str]]:
    # returns (video_id, title, link)
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        entry = next(iter(root.findall("{*}entry")), None)
        if not entry:
            return None
        vid   = entry.find("{*}videoId")
        title = entry.find("{*}title")
        link  = entry.find("{*}link")
        if not (vid is not None and title is not None and link is not None):
            return None
        return vid.text, title.text, link.attrib.get("href", "")
    except Exception:
        return None

def _extract_live_from_html(html_text: str) -> tuple[Optional[str], bool]:
    # (video_id, is_live_now)
    m = _PLAYER_JSON.search(html_text)
    if m:
        try:
            pr = json.loads(m.group(1))
            vid = pr.get("videoDetails", {}).get("videoId")
            is_live = bool(
                pr.get("microformat", {})
                  .get("playerMicroformatRenderer", {})
                  .get("isLive")
            )
            if vid:
                return vid, is_live
        except Exception:
            pass
    m = _DATA_JSON.search(html_text)
    if m:
        try:
            data = json.loads(m.group(1))
            text = json.dumps(data)
            m2 = re.search(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', text)
            return (m2.group(1), True) if m2 else (None, False)
        except Exception:
            pass
    return None, False

async def _resolve_to_channel_id(session: aiohttp.ClientSession, token: str) -> Optional[str]:
    # If it's already a UC ID, use it
    if token.startswith("UC"):
        return token
    # Resolve @handle -> UC… by scraping channel page
    url = f"https://www.youtube.com/@{token}"
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}) as r:
            if r.status != 200:
                return None
            text = await r.text()
        m = re.search(r'"channelId":"(UC[\w-]{21}[AQgw])"', text)
        return m.group(1) if m else None
    except Exception:
        return None

async def yt_latest_upload(session: aiohttp.ClientSession, channel_id: str) -> Optional[tuple[str, str, str]]:
    try:
        async with session.get(_rss_url(channel_id), headers={"User-Agent": USER_AGENT}) as r:
            if r.status != 200:
                return None
            xml = await r.text()
        return _parse_latest_video(xml)
    except Exception:
        return None

async def yt_live_now(session: aiohttp.ClientSession, channel_token: str) -> tuple[Optional[str], Optional[str]]:
    """
    channel_token: UC… or @handle (without '@').
    Returns (live_video_id, watch_url) or (None, None).
    """
    live_url = f"https://www.youtube.com/channel/{channel_token}/live" if channel_token.startswith("UC") \
               else f"https://www.youtube.com/@{channel_token}/live"

    async with session.get(live_url, allow_redirects=True, headers={"User-Agent": USER_AGENT}) as r:
        final_url = str(r.url)
        html_txt = await r.text()

    vid = _video_id_from_url(final_url)
    if vid:
        return vid, f"https://www.youtube.com/watch?v={vid}"

    vid2, is_live = _extract_live_from_html(html_txt)
    if is_live and vid2:
        return vid2, f"https://www.youtube.com/watch?v={vid2}"
    return None, None

# ---------- Twitch helpers (Helix) ----------

class TwitchAuth:
    """Caches an app access token and refreshes when near expiry."""
    def __init__(self, client_id: str | None, client_secret: str | None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None
        self._exp_ts: float = 0.0

    async def get_token(self, session: aiohttp.ClientSession) -> Optional[str]:
        if not self.client_id or not self.client_secret:
            return None
        now = time.time()
        if self._token and now < self._exp_ts - 60:
            return self._token
        # fetch new
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        async with session.post("https://id.twitch.tv/oauth2/token", data=data, headers={"User-Agent": USER_AGENT}) as r:
            if r.status != 200:
                return None
            js = await r.json()
        self._token = js.get("access_token")
        expires_in = js.get("expires_in", 3600)
        self._exp_ts = now + float(expires_in)
        return self._token

    async def headers(self, session: aiohttp.ClientSession) -> Optional[Dict[str, str]]:
        tok = await self.get_token(session)
        if not tok:
            return None
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {tok}",
            "User-Agent": USER_AGENT,
        }

async def twitch_get_user(session: aiohttp.ClientSession, auth: TwitchAuth, login: str) -> Optional[dict]:
    hdrs = await auth.headers(session)
    if not hdrs:
        return None
    async with session.get("https://api.twitch.tv/helix/users", params={"login": login}, headers=hdrs) as r:
        if r.status != 200:
            return None
        js = await r.json()
    data = js.get("data") or []
    return data[0] if data else None

async def twitch_live_now(session: aiohttp.ClientSession, auth: TwitchAuth, user_id: str) -> Optional[dict]:
    """Returns stream object if live, else None."""
    hdrs = await auth.headers(session)
    if not hdrs:
        return None
    async with session.get("https://api.twitch.tv/helix/streams", params={"user_id": user_id}, headers=hdrs) as r:
        if r.status != 200:
            return None
        js = await r.json()
    data = js.get("data") or []
    return data[0] if data else None  # if live

async def twitch_get_games(session: aiohttp.ClientSession, auth: TwitchAuth, game_id: str) -> Optional[str]:
    hdrs = await auth.headers(session)
    if not hdrs:
        return None
    async with session.get("https://api.twitch.tv/helix/games", params={"id": game_id}, headers=hdrs) as r:
        if r.status != 200:
            return None
        js = await r.json()
    data = js.get("data") or []
    return (data[0] or {}).get("name") if data else None

# ---------- The Cog ----------

class StreamWatch(commands.Cog):
    """
    Watches YouTube uploads/Shorts (RSS) + YouTube LIVE (no API) + Twitch LIVE (Helix).
    Commands (Manage Guild required):
      • !ytwatch set <channel-url-or-@handle> [#channel] [@role]
      • !ytwatch role [@role|none]
      • !ytwatch channel [#channel]
      • !ytwatch test
      • !ytwatch off

      • !twitchwatch set <login> [#channel] [@role]
      • !twitchwatch role [@role|none]
      • !twitchwatch channel [#channel]
      • !twitchwatch test
      • !twitchwatch off
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._twitch_auth = TwitchAuth(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    # ----- YouTube commands -----
    @commands.group(name="ytwatch", invoke_without_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def ytwatch(self, ctx: commands.Context):
        await ctx.send("Usage: `ytwatch set <channel-url-or-@handle> [#channel] [@role]`, `ytwatch role [@role|none]`, `ytwatch channel [#channel]`, `ytwatch test`, `ytwatch off`")

    @ytwatch.command(name="set")
    @commands.has_guild_permissions(manage_guild=True)
    async def yt_set(self, ctx: commands.Context, channel_token: str, channel: Optional[discord.TextChannel] = None, role: Optional[discord.Role] = None):
        tok = _extract_channel_token(channel_token) or channel_token.lstrip("@")
        async with aiohttp.ClientSession() as s:
            ucid = await _resolve_to_channel_id(s, tok)
        if not ucid:
            return await ctx.send("❌ I couldn’t resolve that YouTube channel. Please provide a valid `@handle` or channel URL.")
        ch = channel or ctx.channel
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_youtube_watch (guild_id, yt_channel_id, announce_ch_id, ping_role_id)
                VALUES ($1,$2,$3,$4)
                ON CONFLICT (guild_id) DO UPDATE
                SET yt_channel_id=$2, announce_ch_id=$3, ping_role_id=$4
                """,
                ctx.guild.id, ucid, ch.id, (role.id if role else None)
            )
        await ctx.send(f"✅ Now watching **{ucid}**. Announcements → {ch.mention}{' • ping ' + role.mention if role else ''}")

    @ytwatch.command(name="role")
    @commands.has_guild_permissions(manage_guild=True)
    async def yt_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute("UPDATE guild_youtube_watch SET ping_role_id=$2 WHERE guild_id=$1", ctx.guild.id, (role.id if role else None))
        await ctx.send(f"✅ YouTube ping role {'set to ' + role.mention if role else 'cleared'}.")

    @ytwatch.command(name="channel")
    @commands.has_guild_permissions(manage_guild=True)
    async def yt_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        ch = channel or ctx.channel
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute("UPDATE guild_youtube_watch SET announce_ch_id=$2 WHERE guild_id=$1", ctx.guild.id, ch.id)
        await ctx.send(f"✅ YouTube announcements will go to {ch.mention}.")

    @ytwatch.command(name="off")
    @commands.has_guild_permissions(manage_guild=True)
    async def yt_off(self, ctx: commands.Context):
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_youtube_watch WHERE guild_id=$1", ctx.guild.id)
        await ctx.send("🛑 Stopped watching YouTube for this server.")

    @ytwatch.command(name="test")
    @commands.has_guild_permissions(manage_guild=True)
    async def yt_test(self, ctx: commands.Context):
        await self._check_youtube_for_guild(ctx.guild.id, force=True)
        await ctx.send("🔎 Ran a YouTube check.")

    # # ----- Twitch commands -----
    # @commands.group(name="twitchwatch", invoke_without_command=True)
    # @commands.has_guild_permissions(manage_guild=True)
    # async def twwatch(self, ctx: commands.Context):
    #     await ctx.send("Usage: `twitchwatch set <login> [#channel] [@role]`, `twitchwatch role [@role|none]`, `twitchwatch channel [#channel]`, `twitchwatch test`, `twitchwatch off`")

    # @twwatch.command(name="set")
    # @commands.has_guild_permissions(manage_guild=True)
    # async def tw_set(self, ctx: commands.Context, login: str, channel: Optional[discord.TextChannel] = None, role: Optional[discord.Role] = None):
    #     login = login.lstrip("@").lower()
    #     ch = channel or ctx.channel
    #     # Resolve to user_id (so live checks are faster)
    #     async with aiohttp.ClientSession() as s:
    #         user = await twitch_get_user(s, self._twitch_auth, login)
    #     if not user:
    #         return await ctx.send("❌ I couldn’t resolve that Twitch username.")
    #     user_id = user.get("id")
    #     async with self.bot.db_pool.acquire() as conn:
    #         await conn.execute(
    #             """
    #             INSERT INTO guild_twitch_watch (guild_id, twitch_login, twitch_user_id, announce_ch_id, ping_role_id)
    #             VALUES ($1,$2,$3,$4,$5)
    #             ON CONFLICT (guild_id) DO UPDATE
    #             SET twitch_login=$2, twitch_user_id=$3, announce_ch_id=$4, ping_role_id=$5
    #             """,
    #             ctx.guild.id, login, user_id, ch.id, (role.id if role else None)
    #         )
    #     await ctx.send(f"✅ Now watching Twitch **{login}**. Announcements → {ch.mention}{' • ping ' + role.mention if role else ''}")

    # @twwatch.command(name="role")
    # @commands.has_guild_permissions(manage_guild=True)
    # async def tw_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
    #     async with self.bot.db_pool.acquire() as conn:
    #         await conn.execute("UPDATE guild_twitch_watch SET ping_role_id=$2 WHERE guild_id=$1", ctx.guild.id, (role.id if role else None))
    #     await ctx.send(f"✅ Twitch ping role {'set to ' + role.mention if role else 'cleared'}.")

    # @twwatch.command(name="channel")
    # @commands.has_guild_permissions(manage_guild=True)
    # async def tw_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    #     ch = channel or ctx.channel
    #     async with self.bot.db_pool.acquire() as conn:
    #         await conn.execute("UPDATE guild_twitch_watch SET announce_ch_id=$2 WHERE guild_id=$1", ctx.guild.id, ch.id)
    #     await ctx.send(f"✅ Twitch announcements will go to {ch.mention}.")

    # @twwatch.command(name="off")
    # @commands.has_guild_permissions(manage_guild=True)
    # async def tw_off(self, ctx: commands.Context):
    #     async with self.bot.db_pool.acquire() as conn:
    #         await conn.execute("DELETE FROM guild_twitch_watch WHERE guild_id=$1", ctx.guild.id)
    #     await ctx.send("🛑 Stopped watching Twitch for this server.")

    # @twwatch.command(name="test")
    # @commands.has_guild_permissions(manage_guild=True)
    # async def tw_test(self, ctx: commands.Context):
    #     await self._check_twitch_for_guild(ctx.guild.id, force=True)
    #     await ctx.send("🔎 Ran a Twitch check.")

    # ----- Loop -----
    @tasks.loop(minutes=2.0)
    async def loop(self):
        # Grab all guilds with configs
        async with self.bot.db_pool.acquire() as conn:
            yt_rows = await conn.fetch("SELECT guild_id FROM guild_youtube_watch")
            tw_rows = await conn.fetch("SELECT guild_id FROM guild_twitch_watch")

        # Interleave checks a bit
        gids = list({*(int(r["guild_id"]) for r in yt_rows), *(int(r["guild_id"]) for r in tw_rows)})
        for gid in gids:
            await self._check_youtube_for_guild(gid)
            await asyncio.sleep(0.4)
            #await self._check_twitch_for_guild(gid)
            #await asyncio.sleep(0.4)

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    # ----- Checkers -----
    async def _check_youtube_for_guild(self, guild_id: int, force: bool = False):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT yt_channel_id, announce_ch_id, ping_role_id, last_video_id, last_live_id FROM guild_youtube_watch WHERE guild_id=$1",
                guild_id
            )
        if not row:
            return
        yt_channel_id = row["yt_channel_id"]
        announce_ch_id = row["announce_ch_id"]
        ping_role_id   = row["ping_role_id"]
        last_video_id  = row["last_video_id"]
        last_live_id   = row["last_live_id"]

        guild   = self.bot.get_guild(guild_id)
        channel = guild and (guild.get_channel(announce_ch_id) or self.bot.get_channel(announce_ch_id))
        if not (guild and channel):
            return

        async with aiohttp.ClientSession() as s:
            # uploads/shorts via RSS
            latest = await yt_latest_upload(s, yt_channel_id)
            if latest:
                vid, title, link = latest
                if force or (vid and vid != last_video_id):
                    mention = ""
                    if ping_role_id:
                        role = guild.get_role(ping_role_id)
                        if role: mention = role.mention + " "
                    emb = discord.Embed(
                        title=f"📺 New video: {html.unescape(title)}",
                        url=link,
                        description="A new upload just dropped!",
                        color=discord.Color.blurple()
                    )
                    try:
                        await channel.send(f"{mention}{link}", embed=emb)
                        async with self.bot.db_pool.acquire() as conn:
                            await conn.execute("UPDATE guild_youtube_watch SET last_video_id=$2 WHERE guild_id=$1", guild_id, vid)
                    except Exception:
                        pass

            # LIVE now without API
            live_vid, live_url = await yt_live_now(s, yt_channel_id)
            if force or (live_vid and live_vid != last_live_id):
                if live_vid and live_url:
                    mention = ""
                    if ping_role_id:
                        role = guild.get_role(ping_role_id)
                        if role: mention = role.mention + " "
                    emb = discord.Embed(
                        title="🔴 LIVE NOW on YouTube",
                        url=live_url,
                        description="Stream just went live!",
                        color=discord.Color.red()
                    )
                    try:
                        await channel.send(f"{mention}{live_url}", embed=emb)
                        async with self.bot.db_pool.acquire() as conn:
                            await conn.execute("UPDATE guild_youtube_watch SET last_live_id=$2 WHERE guild_id=$1", guild_id, live_vid)
                    except Exception:
                        pass

    async def _check_twitch_for_guild(self, guild_id: int, force: bool = False):
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT twitch_login, twitch_user_id, announce_ch_id, ping_role_id, last_stream_id FROM guild_twitch_watch WHERE guild_id=$1",
                guild_id
            )
        if not row:
            return
        login         = row["twitch_login"]
        user_id       = row["twitch_user_id"]
        announce_ch_id = row["announce_ch_id"]
        ping_role_id   = row["ping_role_id"]
        last_stream_id = row["last_stream_id"]

        guild   = self.bot.get_guild(guild_id)
        channel = guild and (guild.get_channel(announce_ch_id) or self.bot.get_channel(announce_ch_id))
        if not (guild and channel):
            return

        async with aiohttp.ClientSession() as s:
            # ensure user_id cached
            if not user_id:
                user = await twitch_get_user(s, self._twitch_auth, login)
                if not user:
                    return
                user_id = user.get("id")
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute("UPDATE guild_twitch_watch SET twitch_user_id=$2 WHERE guild_id=$1", guild_id, user_id)

            stream = await twitch_live_now(s, self._twitch_auth, user_id)
            if not stream:
                return

            stream_id = stream.get("id")
            title     = stream.get("title") or "Live on Twitch"
            game_id   = stream.get("game_id")
            url       = f"https://twitch.tv/{login}"
            game_name = None
            if game_id:
                game_name = await twitch_get_games(s, self._twitch_auth, game_id)

        if force or (stream_id and stream_id != last_stream_id):
            mention = ""
            if ping_role_id:
                role = guild.get_role(ping_role_id)
                if role: mention = role.mention + " "
            desc = f"{title}"
            if game_name:
                desc += f"\nPlaying **{game_name}**"
            emb = discord.Embed(
                title="🟣 LIVE NOW on Twitch",
                url=url,
                description=desc,
                color=discord.Color.purple()
            )
            try:
                await channel.send(f"{mention}{url}", embed=emb)
                async with self.bot.db_pool.acquire() as conn:
                    await conn.execute("UPDATE guild_twitch_watch SET last_stream_id=$2 WHERE guild_id=$1", guild_id, stream_id)
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(StreamWatch(bot))
