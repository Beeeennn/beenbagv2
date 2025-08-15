# services/image_utils.py
import io
import os
from urllib.parse import urlparse
import discord

from utils.game_helpers import media_url  # you already have this

def is_public_base_url() -> bool:
    """Return True if PUBLIC_BASE_URL is an http(s) URL and not localhost."""
    base = os.getenv("PUBLIC_BASE_URL", "")
    try:
        u = urlparse(base)
        return u.scheme in ("http", "https") and u.hostname not in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False

async def send_embed_with_image(
    ctx,
    embed: discord.Embed,
    image_bytes: bytes,
    filename: str,
    media_id: str | None,
) -> None:
    """
    If PUBLIC_BASE_URL is public and we have a media_id, use URL; otherwise attach bytes.
    This mirrors the fishing/aquarium behavior.
    """
    if is_public_base_url() and media_id:
        embed.set_image(url=media_url(media_id))
        await ctx.send(embed=embed)
    else:
        file = discord.File(io.BytesIO(image_bytes), filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(embed=embed, file=file)
