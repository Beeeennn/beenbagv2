# cogs/mcprofile.py
import re
import json
import base64
import asyncio
from typing import Optional, Dict, Tuple, List
import io
import aiohttp
import discord
from discord.ext import commands

MOJANG_USERNAME_URL = "https://api.mojang.com/users/profiles/minecraft/{username}"
MOJANG_SESSION_URL  = "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
UUID_RE = re.compile(r"^[0-9a-fA-F]{32}$")  # undashed UUID

def dashed_uuid(u: str) -> str:
    u = u.replace("-", "")
    return f"{u[0:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:32]}"

async def mojang_lookup_uuid(session: aiohttp.ClientSession, name: str) -> Optional[str]:
    url = MOJANG_USERNAME_URL.format(username=name)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
        if r.status in (204, 404):
            return None
        r.raise_for_status()
        data = await r.json()
        return data.get("id")

async def mojang_profile_textures(session: aiohttp.ClientSession, uuid_nodash: str) -> Dict:
    url = MOJANG_SESSION_URL.format(uuid=uuid_nodash)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
        r.raise_for_status()
        prof = await r.json()

    name = prof.get("name")
    props = prof.get("properties", [])
    textures_b64 = next((p["value"] for p in props if p.get("name") == "textures"), None)

    skin_url = None
    cape_url = None
    slim = False

    if textures_b64:
        decoded = json.loads(base64.b64decode(textures_b64).decode("utf-8"))
        tex = decoded.get("textures", {})
        skin_obj = tex.get("SKIN")
        cape_obj = tex.get("CAPE")

        if skin_obj:
            skin_url = skin_obj.get("url")
            slim = skin_obj.get("metadata", {}).get("model") == "slim"
        if cape_obj:
            cape_url = cape_obj.get("url")

    return {"name": name, "skin_url": skin_url, "cape_url": cape_url, "slim": slim}

async def fetch_image(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """Return image bytes or None. Small timeout so we don't hang."""
    try:
        timeout = aiohttp.ClientTimeout(connect=3, total=6)
        async with session.get(url, timeout=timeout) as r:
            if r.status != 200:
                return None
            ctype = r.headers.get("Content-Type", "")
            if not ctype.startswith("image/"):
                return None
            return await r.read()
    except Exception:
        return None

class MCProfile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        asyncio.create_task(self.session.close())

    @commands.command(
        name="mcprofile",
        help="Show a Minecraft Java profile. Usage: !mcprofile <username or uuid>"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def mcprofile(self, ctx: commands.Context, handle: str):
        async with ctx.typing():
            # Normalize → undashed UUID
            candidate = handle.replace("-", "")
            if UUID_RE.match(candidate):
                uuid_nodash = candidate.lower()
            else:
                uuid_nodash = await mojang_lookup_uuid(self.session, handle)
                if not uuid_nodash:
                    await ctx.reply(f"❌ I couldn't find a Java account named **{handle}**.")
                    return

            # Fetch textures
            try:
                tex = await mojang_profile_textures(self.session, uuid_nodash)
            except aiohttp.ClientResponseError as e:
                await ctx.reply(f"⚠️ Mojang API error ({e.status}). Try again later.")
                return
            except Exception:
                await ctx.reply("⚠️ Something went wrong talking to Mojang.")
                return

            username = tex.get("name") or handle
            uuid_d = dashed_uuid(uuid_nodash)

            # Build render URLs (we will DOWNLOAD these and ATTACH them)
            avatar_url = f"https://crafatar.com/avatars/{uuid_nodash}?size=160&overlay"
            head3d_url = f"https://crafatar.com/renders/head/{uuid_nodash}?scale=10&overlay"
            raw_skin_png = f"https://crafatar.com/skins/{uuid_nodash}"
            raw_cape_png = f"https://crafatar.com/capes/{uuid_nodash}"

            # Try to fetch avatar + head; fall back gracefully
            avatar_bytes = await fetch_image(self.session, avatar_url)
            head_bytes   = await fetch_image(self.session, head3d_url)

        # Build embed (outside typing to avoid long holds)
        model_label = "Alex (slim)" if tex["slim"] else "Steve (classic)"
        has_cape = "Yes" if tex["cape_url"] else "No"

        em = discord.Embed(
            title=f"{username}'s Minecraft Profile",
            description=f"UUID: `{uuid_d}`",
            color=discord.Color.green()
        )

        files: List[discord.File] = []

        # Prefer attached images so Discord never has to fetch external URLs
        if avatar_bytes:
            files.append(discord.File(fp=io.BytesIO(avatar_bytes), filename="avatar.png"))
            em.set_thumbnail(url="attachment://avatar.png")
        else:
            # In the rare case avatar couldn't be fetched, skip thumbnail
            pass

        if head_bytes:
            files.append(discord.File(fp=io.BytesIO(head_bytes), filename="head.png"))
            em.set_image(url="attachment://head.png")
        elif avatar_bytes:
            # fall back to using the face as the big image
            em.set_image(url="attachment://avatar.png")

        em.add_field(name="Model", value=model_label, inline=True)
        em.add_field(name="Cape", value=has_cape, inline=True)
        em.add_field(name="Skin (PNG)", value=f"[Download]({raw_skin_png})", inline=False)
        if tex["cape_url"]:
            em.add_field(name="Cape (PNG)", value=f"[Download]({raw_cape_png})", inline=False)
        em.add_field(name="NameMC", value=f"https://namemc.com/profile/{uuid_d}", inline=False)

        if files:
            await ctx.send(embed=em, files=files)
        else:
            # Absolute worst case: no images fetched—still send text info
            await ctx.send(embed=em)

async def setup(bot: commands.Bot):
    await bot.add_cog(MCProfile(bot))
