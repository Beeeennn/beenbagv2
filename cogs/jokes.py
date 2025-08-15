# cogs/images.py
import re
from io import BytesIO
from typing import Optional

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter
from core.decorators import *

NUM_RE = re.compile(r"^\d*\.?\d+$")

def _circular_feather_mask(size: tuple[int, int], feather_ratio: float = 0.08) -> Image.Image:
    """Create a circular alpha mask with feathered (blurred) edges."""
    w, h = size
    r = int(min(w, h) * feather_ratio)
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, w - 1, h - 1), fill=255)
    if r > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=r))
    return mask

async def _fetch_avatar(member: discord.abc.User, size: int = 512) -> Image.Image:
    # Get a static PNG of the avatar at a sane size
    asset = member.display_avatar.replace(size=size)
    data = await asset.read()
    img = Image.open(BytesIO(data)).convert("RGBA")
    # Some avatars are not square; make square by fitting on transparent canvas
    if img.width != img.height:
        side = max(img.width, img.height)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        offset = ((side - img.width) // 2, (side - img.height) // 2)
        canvas.paste(img, offset)
        img = canvas
    return img

class Images(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="baby")
    @premium_fixed_cooldown(free_seconds=600,premium_seconds=5,bucket=commands.BucketType.member)
    async def baby(self, ctx: commands.Context, *args: str):
        """
        Usage:
        !baby @parent1 @parent2
        !baby @parent1 0.4 @parent2          # optional scale (0.1–0.9)
        !baby 0.5 @parent1 @parent2          # number can be anywhere
        """
        # Parse mentions (first two are used)
        mentions = ctx.message.mentions
        if len(mentions) < 2:
            return await ctx.send("Please mention **two users**. Example: `!baby @A @B`")

        p1, p2 = mentions[0], mentions[1]

        # Parse optional numeric scale anywhere in the args
        scale: Optional[float] = None
        for tok in args:
            if NUM_RE.match(tok):
                try:
                    scale = float(tok)
                except ValueError:
                    pass
        if scale is None:
            scale = 0.45
        scale = max(0.15, min(scale, 0.9))

        # Fetch avatars
        try:
            base = await _fetch_avatar(p2, size=512)  # background
            overlay = await _fetch_avatar(p1, size=512)
        except Exception:
            return await ctx.send("I couldn’t fetch one of those avatars. Try again?")

        # Resize overlay relative to base
        ow = int(base.width * scale)
        overlay = overlay.resize((ow, ow), Image.LANCZOS)

        # Apply feathered circular mask to overlay
        mask = _circular_feather_mask(overlay.size, feather_ratio=0.12)
        overlay.putalpha(mask)

        # Position overlay in the center (adjust y for different placement)
        x = (base.width - ow) // 2
        y = (base.height - ow) // 2
        composed = base.copy()
        composed.alpha_composite(overlay, (x, y))

        # Save to buffer
        buf = BytesIO()
        composed.save(buf, format="PNG")
        buf.seek(0)

        # Create embed
        embed = discord.Embed(
            title="👶 It's a baby!",
            description=f"{p1.display_name} + {p2.display_name} = ❤️",
            color=discord.Color.pink()
        )
        embed.set_image(url="attachment://baby.png")

        # Send embed with attachment
        file = discord.File(buf, filename="baby.png")
        await ctx.send(embed=embed, file=file)
    @baby.error
    async def baby_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await send_premium_cooldown_message(ctx, error)

async def setup(bot: commands.Bot):
    await bot.add_cog(Images(bot))
