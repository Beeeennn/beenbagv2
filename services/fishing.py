from datetime import datetime, timedelta
from constants import MINECRAFT_COLORS,FISHTYPES,FISHINGCHANCE, TIER_ORDER
from utils.game_helpers import ensure_player, save_image_bytes, resolve_member, media_url, gid_from_ctx,lb_inc
import random
import discord
import io
from PIL import Image, ImageOps
import os
from services import achievements
def tint_image(image: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
    """Tint grayscale-ish sprites while keeping alpha."""
    img = image.convert("RGBA")
    # take the red channel as luminance (your assets use R as brightness)
    r, g, b, a = img.split()
    # colorize using the same color for black/white so it scales by luminance
    # map 0->(0,0,0), 255->tint
    gray = r.convert("L")
    colorized = ImageOps.colorize(gray, black=(0,0,0), white=tint).convert("RGBA")
    colorized.putalpha(a)
    return colorized

async def make_fish(pool, ctx,fish_path: str):

    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    
    # Pick 2 distinct colors
    color_names = random.sample(list(MINECRAFT_COLORS.keys()), 2)
    color1 = MINECRAFT_COLORS[color_names[0]]
    color2 = MINECRAFT_COLORS[color_names[1]]
    typef = random.choice(FISHTYPES)
    async with pool.acquire() as conn:
        await ensure_player(conn,ctx.author.id,guild_id)
        await lb_inc(conn,"fish_caught",user_id,guild_id,1)
        # 1) Fetch all usable rods
        rods = await conn.fetch(
            """
            SELECT tier, uses_left
              FROM tools
             WHERE user_id = $1
               AND guild_id = $2
               AND tool_name = 'fishing_rod'
               AND uses_left > 0
            """,
            user_id, guild_id
        )

        if not rods:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"❌ You need a fishing rod with at least 1 use to mine! Craft one with `{ctx.clean_prefix}craft fishing rod`."
            )
        # 2) Determine your highest tier pickaxe
        owned_tiers = {r["tier"] for r in rods}
        best_tier = None
        for tier in reversed(TIER_ORDER):
            if tier in owned_tiers:
                best_tier = tier
                break        
        # 3) Consume 1 use on that rod
        await conn.execute(
            """
            UPDATE tools
               SET uses_left = uses_left - 1
             WHERE user_id = $1
             AND guild_id = $2
               AND tool_name = 'fishing_rod'
               AND tier = $3
               AND uses_left > 0
            """,
            user_id,guild_id,best_tier
        )
        chance = random.randint(0,100)
        if chance>FISHINGCHANCE[best_tier]:
            
            await conn.execute(
                """
                INSERT INTO aquarium (user_id,guild_id,color1,color2,type)
                VALUES ($1,$2,$3,$4,$5)
                """,
                user_id,guild_id,color_names[0],color_names[1],typef
            )
            await achievements.try_grant(pool,ctx,user_id,"first_fish")
        else:
            return await ctx.send("You caught a sea pickle, yuck!!! you throw it back in the ocean")
            
    base_path = f"{fish_path}{typef}/base.png"
    overlay_path = f"{fish_path}{typef}/overlay.png"
    base = Image.open(base_path).convert("RGBA")
    overlay = Image.open(overlay_path).convert("RGBA")

    tinted_base = tint_image(base, color1)
    tinted_overlay = tint_image(overlay, color2)

    result = Image.alpha_composite(tinted_base, tinted_overlay)
    # 🔍 Scale up 20× using nearest neighbor to preserve pixel style
    scale = 20
    new_size = (result.width * scale, result.height * scale)
    result = result.resize(new_size, resample=Image.NEAREST)
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    image_bytes = buf.getvalue()
    async with pool.acquire() as conn:
        media_id = await save_image_bytes(conn, image_bytes, "image/png")
    image_url = media_url(media_id)

    embed = discord.Embed(
        description=f"🎣 You used your **{best_tier} fishing rod** to catch a **{color_names[0]} and {color_names[1]} {typef}**!"
    )
    embed.set_image(url=image_url)
    await ctx.send(embed=embed)


async def generate_aquarium(pool, ctx, who):
    background_path="assets/fish/aquarium.png"
    # Resolve who → Member (or fallback to author)
    guild_id = gid_from_ctx(ctx)
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")  # or "Member not found."

    # Now you’ve got a real Member with .id, .display_name, etc.
    user_id = member.id
    async with pool.acquire() as conn:

        await conn.execute("""
            DELETE FROM aquarium
            WHERE time_caught < NOW() - INTERVAL '1 day'
        """)
        row = await conn.fetch("""
        SELECT color1, color2, type
        FROM aquarium                 
        WHERE user_id = $1
        AND guild_id = $2
        ORDER BY time_caught DESC
        LIMIT 30    
                         """,
                         user_id,guild_id)
    fish_specs = []
    for r in row:
        fish_specs += [[r["color1"],r["color2"],r["type"]]]

    unique_color1 = set(f[0] for f in fish_specs)
    unique_color2 = set(f[1] for f in fish_specs)
    unique_types  = set(f[2] for f in fish_specs)

    food = len(unique_color1) + len(unique_color2) + len(unique_types)
    if len(fish_specs) > 30:
        raise ValueError("You can only place up to 30 fish.")
    elif len(fish_specs) == 30:
        achievements.try_grant(pool,ctx,user_id,"full_aquarium")
    if food == 38:
        achievements.try_grant(pool,ctx,user_id,"full_food")
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
    for spec in fish_specs:
        color1_name, color2_name, fish_type = spec
        color1 = MINECRAFT_COLORS.get(color1_name)
        color2 = MINECRAFT_COLORS.get(color2_name)
        if not color1 or not color2:
            print(f"⚠️ Invalid color name: {color1_name} or {color2_name}")
            continue
        base_path = f"assets/fish/{fish_type}/base.png"
        overlay_path = f"assets/fish/{fish_type}/overlay.png"
        if not (os.path.exists(base_path) and os.path.exists(overlay_path)):
            print(f"⚠️ Missing image for fish type: {fish_type}")
            continue
        base = Image.open(base_path).convert("RGBA")
        overlay = Image.open(overlay_path).convert("RGBA")
        tinted_base =  tint_image(base, color1)
        tinted_overlay = tint_image(overlay, color2)
        fish_image = Image.alpha_composite(tinted_base, tinted_overlay)
        scale = 1
        new_size = (fish_image.width * scale, fish_image.height * scale)
        fish_image = fish_image.resize(new_size, resample=Image.NEAREST)

        # Randomly flip 50% of fish
        if random.choice([True, False]):
            fish_image = ImageOps.mirror(fish_image)

        # Place it
        tries = 0
        while tries < 1000:
            x = random.randint(edge_buffer, width - fish_size*scale - edge_buffer)
            y = random.randint(edge_buffer, height - fish_size*scale - edge_buffer)
            if is_valid_position(x, y):
                aquarium.alpha_composite(fish_image, (x, y))
                placed_positions.append((x, y))
                break
            tries += 1
        else:
            print(f"⚠️ Could not place fish {spec} after 1000 attempts")
    result = aquarium
    scale = 4
    new_size = (result.width * scale, result.height * scale)
    result = result.resize(new_size, resample=Image.NEAREST)
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    image_bytes = buf.getvalue()
    async with pool.acquire() as conn:
        media_id = await save_image_bytes(conn, image_bytes, "image/png")
    image_url = media_url(media_id)

    embed = discord.Embed(
        title=f"{member.display_name}'s Aquarium",
        description=f"Generates **{food}** fish food every 30 minutes with **{len(fish_specs)}** fish"
    )
    embed.set_image(url=image_url)
    await ctx.send(embed=embed)