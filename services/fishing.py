import os
import io
import random
import discord
from urllib.parse import urlparse
from PIL import Image, ImageOps
from datetime import datetime, timedelta

from constants import MINECRAFT_COLORS, FISHTYPES, FISHINGCHANCE, TIER_ORDER
from utils.game_helpers import (
    ensure_player, save_image_bytes, resolve_member,
    media_url, gid_from_ctx, lb_inc
)
from services import achievements

# ---------------- helpers for local vs public image sending ---------------- #

def _is_public_base_url() -> bool:
    """Return True if PUBLIC_BASE_URL is an http(s) URL and not localhost."""
    base = os.getenv("PUBLIC_BASE_URL", "")
    try:
        u = urlparse(base)
        return u.scheme in ("http", "https") and u.hostname not in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False

async def _send_embed_with_image(ctx, embed: discord.Embed, image_bytes: bytes, filename: str, media_id: str | None):
    """
    If PUBLIC_BASE_URL is public and we have a media_id, use URL; otherwise attach bytes.
    This makes embeds work both locally and globally.
    """
    if _is_public_base_url() and media_id:
        embed.set_image(url=media_url(media_id))
        await ctx.send(embed=embed)
    else:
        file = discord.File(io.BytesIO(image_bytes), filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(embed=embed, file=file)

# ---------------- image tint utility (unchanged) ---------------- #

def tint_image(image: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
    """Tint grayscale-ish sprites while keeping alpha."""
    img = image.convert("RGBA")
    r, g, b, a = img.split()
    gray = r.convert("L")
    colorized = ImageOps.colorize(gray, black=(0,0,0), white=tint).convert("RGBA")
    colorized.putalpha(a)
    return colorized

# ---------------- fishing: generate fish + send embed ---------------- #

async def make_fish(pool, ctx, fish_path: str):
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)

    color_names = random.sample(list(MINECRAFT_COLORS.keys()), 2)
    color1 = MINECRAFT_COLORS[color_names[0]]
    color2 = MINECRAFT_COLORS[color_names[1]]
    typef = random.choice(FISHTYPES)

    async with pool.acquire() as conn:
        await ensure_player(conn, user_id, guild_id)
        await lb_inc(conn, "fish_caught", user_id, guild_id, 1)

        # fetch rods
        rods = await conn.fetch(
            """
            SELECT tier, uses_left
            FROM tools
            WHERE user_id = $1 AND guild_id = $2
              AND tool_name = 'fishing_rod' AND uses_left > 0
            """,
            user_id, guild_id
        )
        if not rods:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"❌ You need a fishing rod with at least 1 use to fish! Craft one with `{ctx.clean_prefix}craft fishing rod wood`."
            )

        # highest tier rod
        owned_tiers = {r["tier"] for r in rods}
        best_tier = next((t for t in reversed(TIER_ORDER) if t in owned_tiers), None)
        if not best_tier:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("❌ You have no usable fishing rod.")

        # consume use
        await conn.execute(
            """
            UPDATE tools
            SET uses_left = uses_left - 1
            WHERE user_id = $1 AND guild_id = $2
              AND tool_name = 'fishing_rod' AND tier = $3 AND uses_left > 0
            """,
            user_id, guild_id, best_tier
        )

        # success check
        chance = random.randint(0, 100)
        if chance > FISHINGCHANCE[best_tier]:
            await conn.execute(
                """
                INSERT INTO aquarium (user_id, guild_id, color1, color2, type)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user_id, guild_id, color_names[0], color_names[1], typef
            )
            await achievements.try_grant(pool, ctx, user_id, "first_fish")
        else:
            return await ctx.send("You caught a sea pickle, yuck! You throw it back into the ocean.")

    # compose sprite
    base_path = f"{fish_path}{typef}/base.png"
    overlay_path = f"{fish_path}{typef}/overlay.png"
    base = Image.open(base_path).convert("RGBA")
    overlay = Image.open(overlay_path).convert("RGBA")

    tinted_base = tint_image(base, color1)
    tinted_overlay = tint_image(overlay, color2)
    result = Image.alpha_composite(tinted_base, tinted_overlay)

    # upscale for nicer preview
    result = result.resize((result.width * 20, result.height * 20), resample=Image.NEAREST)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    image_bytes = buf.getvalue()

    # save to media (optional but kept for prod URLs)
    async with pool.acquire() as conn:
        media_id = await save_image_bytes(conn, image_bytes, "image/png")

    embed = discord.Embed(
        description=f"🎣 You used your **{best_tier} fishing rod** to catch a **{color_names[0]} & {color_names[1]} {typef}**!"
    )

    # ✅ URL in prod / tunnel, attachment in local
    await _send_embed_with_image(ctx, embed, image_bytes, "fish.png", media_id)

# ---------------- aquarium: compose grid + send embed ---------------- #

async def generate_aquarium(pool, ctx, who):
    background_path = "assets/fish/aquarium.png"
    guild_id = gid_from_ctx(ctx)

    # resolve member
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")
    user_id = member.id

    async with pool.acquire() as conn:
        # cleanup old fish
        await conn.execute("DELETE FROM aquarium WHERE time_caught < NOW() - INTERVAL '1 day'")
        rows = await conn.fetch(
            """
            SELECT color1, color2, type
            FROM aquarium
            WHERE user_id = $1 AND guild_id = $2
            ORDER BY time_caught DESC
            LIMIT 30
            """,
            user_id, guild_id
        )

    fish_specs = [[r["color1"], r["color2"], r["type"]] for r in rows]

    unique_color1 = set(f[0] for f in fish_specs)
    unique_color2 = set(f[1] for f in fish_specs)
    unique_types  = set(f[2] for f in fish_specs)
    food = len(unique_color1) + len(unique_color2) + len(unique_types)

    if len(fish_specs) > 30:
        return await ctx.send("You can only place up to 30 fish.")
    elif len(fish_specs) == 30:
        await achievements.try_grant(pool, ctx, user_id, "full_aquarium")
    if food == 38:
        await achievements.try_grant(pool, ctx, user_id, "full_food")

    # compose aquarium image
    aquarium = Image.open(background_path).convert("RGBA")
    width, height = aquarium.size
    fish_size = 12
    edge_buffer = 6
    fish_buffer = 2
    placed_positions = []

    def is_valid_position(x, y):
        for px, py in placed_positions:
            if abs(x - px) < fish_size + fish_buffer and abs(y - py) < fish_size + fish_buffer:
                return False
        return True

    for color1_name, color2_name, fish_type in fish_specs:
        color1 = MINECRAFT_COLORS.get(color1_name)
        color2 = MINECRAFT_COLORS.get(color2_name)
        if not color1 or not color2:
            continue

        base_path = f"assets/fish/{fish_type}/base.png"
        overlay_path = f"assets/fish/{fish_type}/overlay.png"
        if not (os.path.exists(base_path) and os.path.exists(overlay_path)):
            continue

        base = Image.open(base_path).convert("RGBA")
        overlay = Image.open(overlay_path).convert("RGBA")
        fish_image = Image.alpha_composite(tint_image(base, color1), tint_image(overlay, color2))

        # random mirror
        if random.choice([True, False]):
            fish_image = ImageOps.mirror(fish_image)

        # place
        for _ in range(1000):
            x = random.randint(edge_buffer, width - fish_size - edge_buffer)
            y = random.randint(edge_buffer, height - fish_size - edge_buffer)
            if is_valid_position(x, y):
                aquarium.alpha_composite(fish_image, (x, y))
                placed_positions.append((x, y))
                break

    # upscale for preview
    result = aquarium.resize((aquarium.width * 4, aquarium.height * 4), resample=Image.NEAREST)

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    image_bytes = buf.getvalue()

    # save for URL mode
    async with pool.acquire() as conn:
        media_id = await save_image_bytes(conn, image_bytes, "image/png")

    embed = discord.Embed(
        title=f"{member.display_name}'s Aquarium",
        description=f"Generates **{food}** fish food every 30 minutes with **{len(fish_specs)}** fish"
    )

    # ✅ URL in prod / tunnel, attachment in local
    await _send_embed_with_image(ctx, embed, image_bytes, "aquarium.png", media_id)

async def missing_fish(db_pool, ctx, who: str | None = None):
    """Show which fish types, base colours, and pattern colours you're missing in your aquarium."""
    guild_id = gid_from_ctx(ctx)

    # whose aquarium?
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")
    user_id = member.id

    async with db_pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT color1, color2, type
            FROM aquarium
            WHERE user_id = $1 AND guild_id = $2 AND time_caught >= NOW() - INTERVAL '1 day'
            ORDER BY time_caught DESC
            LIMIT 30
            """,
            user_id, guild_id
        )

    owned_base    = {r["color1"] for r in rows}
    owned_pattern = {r["color2"] for r in rows}
    owned_types   = {r["type"] for r in rows}

    all_types   = set(FISHTYPES)
    all_colors  = set(MINECRAFT_COLORS.keys())

    missing_types    = sorted(all_types - owned_types)
    missing_base     = sorted(all_colors - owned_base)
    missing_pattern  = sorted(all_colors - owned_pattern)

    embed = discord.Embed(
        title=f"{member.display_name}'s Missing Fish",
        description="Here are the fish attributes you still need to collect:"
    )

    if missing_types:
        embed.add_field(
            name=f"Missing Types ({len(missing_types)})",
            value=", ".join(missing_types),
            inline=False
        )
    if missing_base:
        embed.add_field(
            name=f"Missing Base Colours ({len(missing_base)})",
            value=", ".join(missing_base),
            inline=False
        )
    if missing_pattern:
        embed.add_field(
            name=f"Missing Pattern Colours ({len(missing_pattern)})",
            value=", ".join(missing_pattern),
            inline=False
        )

    if not (missing_types or missing_base or missing_pattern):
        embed.description = f"✅ {member.display_name} has collected every type, base colour, and pattern colour!"

    await ctx.send(embed=embed)