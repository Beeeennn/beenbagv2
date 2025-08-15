# cogs/levels.py
import io
from typing import Optional, Tuple
import os
import discord
from discord.ext import commands

from utils.game_helpers import resolve_member, get_level_from_exp, gid_from_ctx, save_image_bytes
from constants import LEVEL_EXP
from services.image_utils import send_embed_with_image  # NEW

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    PIL_OK = True
except Exception:
    PIL_OK = False


# ---------- Utilities ----------
def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _progress_tuple(total_exp: int, current_level: int):
    """Return (exp_into_level, span_this_level, next_level_cap)."""
    req_current = LEVEL_EXP.get(current_level, 0)
    max_level = max(LEVEL_EXP.keys())
    if current_level >= max_level:
        return (0, 0, req_current)
    req_next = LEVEL_EXP[current_level + 1]
    into = total_exp - req_current
    span = req_next - req_current
    return (into, span, req_next)


async def _fetch_rank_and_exp(conn, guild_id: int, user_id: int):
    """Single query for exp + rank within guild."""
    row = await conn.fetchrow(
        """
        WITH ranked AS (
            SELECT discord_id,
                   guild_id,
                   experience,
                   RANK() OVER (PARTITION BY guild_id ORDER BY experience DESC) AS rk
            FROM accountinfo
        )
        SELECT experience, rk
          FROM ranked
         WHERE discord_id = $1 AND guild_id = $2
        """,
        user_id,
        guild_id,
    )
    if row:
        return int(row["experience"]), int(row["rk"])
    return 0, None


def _circle_crop(im: "Image.Image", size: int) -> "Image.Image":
    im = im.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(im, (0, 0), mask)
    return out


def _load_font(size: int) -> "ImageFont.FreeTypeFont":
    """
    Load a real TTF so sizes actually differ.
    Drop a font in assets/fonts/ (e.g., Minecraftia.ttf or PressStart2P-Regular.ttf).
    """
    candidates = [
        "assets/fonts/PressStart2P-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    # Last resort (tiny bitmap)
    return ImageFont.load_default()


# ---------- Card Rendering ----------
def _make_rank_card(
    member: discord.Member,
    total_exp: int,
    level: int,
    rank: Optional[int],
    exp_into: int,
    exp_span: int,
    background_name=None
):
    """
    Return (rgba_bytes, (W,H)) for the rank card.
    All UI elements are drawn onto a transparent overlay and then
    alpha-composited over the background (true overlay behavior).
    """
    W, H = 1200, 400

    # 1) Load chosen background if it exists
    bg = None
    if background_name:
        path = os.path.join("assets", "others", "expbg", background_name)
        if os.path.exists(path):
            bg = Image.open(path).convert("RGBA").resize((W, H))

    # 2) Fallback to black if not found
    if bg is None:
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    # --- Create a transparent overlay to draw UI on ---
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Fonts
    font_big = _load_font(50)    # username
    font_med = _load_font(40)    # level/rank pill
    font_prog = _load_font(30)   # progress numbers
    font_small = _load_font(30)  # total EXP

    # Panel (overlay, semi‑transparent)
    # Using rounded rect so it looks nicer on photos
    panel_bounds = (20, 20, W - 20, H - 20)
    draw.rounded_rectangle(panel_bounds, radius=24, fill=(255, 255, 255, 28))

    # Username
    uname = member.display_name
    draw.text((330, 50), uname, font=font_big, fill=(255, 255, 255, 255))

    # Pills
    pill_y = 155
    pill_h = 76

    def pill(x1: int, text: str) -> int:
        pad = 22
        tw = draw.textlength(text, font=font_med)
        w = int(tw + pad * 2)
        r = pill_h // 2
        # pill background on overlay
        draw.rounded_rectangle(
            (x1, pill_y, x1 + w, pill_y + pill_h),
            radius=r,
            fill=(255, 255, 255, 48),
        )
        # pill text
        draw.text(
            (x1 + pad, pill_y + (pill_h - font_med.size) // 2 - 2),
            text,
            font=font_med,
            fill=(255, 255, 255, 255),
        )
        return x1 + w + 20

    x = 330
    x = pill(x, f"LVL {level}")
    if rank is not None:
        x = pill(x, f"Rank #{rank}")

    # Progress bar (drawn entirely on overlay)
    bar_x, bar_y, bar_w, bar_h = 330, 255, 800, 54
    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
        radius=27,
        fill=(255, 255, 255, 48),
    )

    pct = 0.0 if exp_span <= 0 else max(0.0, min(1.0, exp_into / exp_span))
    fill_w = int(bar_w * pct)
    if fill_w > 0:
        draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h),
            radius=27,
            fill=(255, 255, 255, 220),
        )

    prog_text = f"{_fmt_int(exp_into)}/{_fmt_int(exp_span)}"
    tw = draw.textlength(prog_text, font=font_prog)
    draw.text(
        (bar_x + bar_w - tw - 16, bar_y + (bar_h - font_prog.size) // 2 - 2),
        prog_text,
        font=font_prog,
        fill=(0, 0, 0, 255),
    )

    # Total EXP
    draw.text(
        (330, 330),
        f"Total: {_fmt_int(total_exp)} EXP",
        font=font_small,
        fill=(240, 240, 245, 255),
    )

    # --- Composite overlay over background (true overlay, no overwrites) ---
    composed = Image.alpha_composite(bg, overlay)

    # Return raw RGBA bytes for later composition with avatar
    return composed.tobytes(), (W, H)


def _compose_with_avatar(
    bg_rgba_bytes: bytes, size_wh: Tuple[int, int], avatar_bytes: bytes
) -> bytes:
    W, H = size_wh
    bg = Image.frombytes("RGBA", (W, H), bg_rgba_bytes)

    # Load + circle-crop the avatar
    avi = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avi = _circle_crop(avi, 240)

    # Circular glow with no square corners (optional; remove for no glow)
    glow = Image.new("RGBA", (270, 270), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((0, 0, 270, 270), fill=(255, 255, 255, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    bg.alpha_composite(glow, (40, 40))

    # Paste the avatar using its alpha as a mask (no square)
    bg.paste(avi, (55, 55), avi)

    out = io.BytesIO()
    bg.save(out, "PNG")
    out.seek(0)
    return out.getvalue()

async def _fetch_selected_background(conn, guild_id, user_id):
    return await conn.fetchval(
        "SELECT selected_background FROM user_settings WHERE user_id=$1 AND guild_id=$2",
        user_id, guild_id
    )
# ---------- Command entry ----------
async def rank_cmd(pool, ctx, who):
    guild_id = ctx.guild.id if ctx.guild else None

    # Resolve member
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("❌ Member not found.")

    async with pool.acquire() as conn:
        total_exp, server_rank = await _fetch_rank_and_exp(conn, guild_id, member.id)
        bg_name = await _fetch_selected_background(conn, guild_id, member.id)
    level = get_level_from_exp(total_exp)
    into, span, _next_cap = _progress_tuple(total_exp, level)

    if not PIL_OK:
        # Fallback simple embed
        em = discord.Embed(color=discord.Color.blurple())
        em.set_author(name=str(member), icon_url=member.display_avatar.url)
        em.add_field(name="Level", value=str(level))
        if span > 0:
            pct = int((into / span) * 100)
            em.add_field(
                name="Progress",
                value=f"{_fmt_int(into)}/{_fmt_int(span)} ({pct}%)",
                inline=False,
            )
        em.add_field(name="Total EXP", value=_fmt_int(total_exp))
        if server_rank is not None:
            em.set_footer(text=f"Server Rank #{server_rank}")
        return await ctx.send(embed=em)

    # Build background + text
    bg_bytes, size_wh = _make_rank_card(
        member, total_exp, level, server_rank, into, span, background_name=bg_name
    )

    # Avatar PNG
    avatar_asset = member.display_avatar.with_size(256).with_format("png")
    avatar_bytes = await avatar_asset.read()

    # Compose final PNG
    png_bytes = _compose_with_avatar(bg_bytes, size_wh, avatar_bytes)

    # Save to media store for public URL mode
    async with pool.acquire() as conn:
        media_id = await save_image_bytes(conn, png_bytes, "image/png")

    # One send: URL if public base, attachment otherwise
    em = discord.Embed(color=discord.Color.blurple())
    em.set_footer(text="You can buy other backgrounds using !bg buy")  # NEW
    await send_embed_with_image(ctx, em, png_bytes, "rank.png", media_id)
