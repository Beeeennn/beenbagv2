# tasks/spawns.py
import asyncio, random, io
from datetime import datetime, timedelta, timezone
from PIL import Image
import discord
from constants import MOBS, NOT_SPAWN_MOBS, RARITIES, COLOR_MAP
from utils.prefixes import get_cached_prefix
import os

def _tasks(bot): return bot.state.setdefault("spawn_tasks", {})

# tasks/spawns.py
import asyncio

def _task_dict(bot):
    # create the dict if missing
    store = getattr(bot, "state", None)
    if store is None:
        bot.state = store = {}
    return store.setdefault("spawn_tasks", {})

def start_all_guild_spawn_tasks(bot):
    for g in bot.guilds:
        start_guild_spawn_task(bot, g.id)

def start_guild_spawn_task(bot, guild_id: int):
    stop_guild_spawn_task(bot, guild_id)
    t = asyncio.create_task(spawn_loop_for_guild(bot, guild_id))
    _task_dict(bot)[guild_id] = t

def stop_guild_spawn_task(bot, guild_id: int):
    t = _task_dict(bot).pop(guild_id, None)
    if t and not t.done():
        t.cancel()

async def get_spawn_channels_for_guild(bot, guild_id: int):
    rows = await bot.db_pool.fetch("SELECT channel_id FROM guild_spawn_channels WHERE guild_id=$1", guild_id)
    chans = []
    for r in rows:
        ch = bot.get_channel(r["channel_id"])
        if isinstance(ch, (discord.TextChannel, discord.Thread)):
            p = ch.permissions_for(ch.guild.me)
            if p.view_channel and p.send_messages: chans.append(ch)
    return chans

async def spawn_loop_for_guild(bot, guild_id: int):
    await bot.wait_until_ready()
    while True:
        try:
            channels = await get_spawn_channels_for_guild(bot, guild_id)
            if channels:
                await spawn_once_in_channel(bot, random.choice(channels))
            await asyncio.sleep(random.randint(120, 480))
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(10)
# tasks/spawns.py
import asyncio
import logging
import random
from datetime import datetime, timezone
from services.discord_limits import call_with_gate

# (Optional) per‑channel lock prevents bursts in the same channel
_channel_locks = {}
def _lock_for(chan_id: int):
    _channel_locks.setdefault(chan_id, asyncio.Lock())
    return _channel_locks[chan_id]

import asyncio, logging, random
from datetime import datetime, timezone
from services.discord_limits import call_with_gate

# (keep your existing _lock_for)

async def watch_spawn_expiry(bot, spawn_id, channel_id, message_id, mob_name, expires_at):
    """Sleeps until expiry, removes DB row if still active, deletes the spawn message via PartialMessage,
    and posts a gentle 'escaped' notice — all behind rate-limit/backoff guards."""
    try:
        # Sleep until the exact expiry time (with a tiny random jitter so many tasks don't wake at once)
        now = datetime.now(timezone.utc)
        delay = max(0.0, (expires_at - now).total_seconds()) + random.uniform(0, 0.3)
        if delay > 0:
            await asyncio.sleep(delay)

        # Check DB — bail if already caught
        async with bot.db_pool.acquire() as conn:
            still_there = await conn.fetchval(
                "SELECT 1 FROM active_spawns WHERE spawn_id = $1",
                spawn_id
            )
            if not still_there:
                return

            # Remove the DB entry first (idempotent)
            await conn.execute("DELETE FROM active_spawns WHERE spawn_id = $1", spawn_id)

        # Get channel (prefer cache, otherwise fetch once)
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                # IMPORTANT: pass a factory (lambda), not a coroutine object
                channel = await call_with_gate(lambda: bot.fetch_channel(channel_id),
                                               op_name="fetch_channel")
            except Exception as e:
                logging.warning(f"[spawn_expiry] cannot fetch channel {channel_id}: {e}")
                return

        # Serialize operations in this channel to avoid mini-stampedes
        async with _lock_for(channel.id):
            # 1) Delete the original message via PartialMessage (NO fetch)
            try:
                pm = channel.get_partial_message(message_id)
                await call_with_gate(lambda: pm.delete(), op_name="spawn_delete")
            except Exception as e:
                # Not fatal (it may already be gone, or permissions missing)
                logging.info(f"[spawn_expiry] delete skipped/failure for {message_id}: {e}")

            # 2) Post a lightweight announcement
            try:
                await call_with_gate(
                    lambda: channel.send(f"**{mob_name}** escaped, maybe next time", delete_after=60),
                    op_name="spawn_announce"
                )
            except Exception as e:
                logging.info(f"[spawn_expiry] announce failed in {channel.id}: {e}")

            # Small spacing to be nice to the bucket if many expiries are queued
            await asyncio.sleep(0.25)

    except asyncio.CancelledError:
        # Task cancelled cleanly (e.g., shutdown)
        raise
    except Exception as e:
        logging.exception(f"[spawn_expiry] unexpected error for spawn_id={spawn_id}: {e}")

    
async def spawn_once_in_channel(bot, chan):
    # ---- pick a mob exactly like before ----
    mob_names_all = list(MOBS.keys())
    mob_names = [m for m in mob_names_all if m not in NOT_SPAWN_MOBS]
    rarities  = [MOBS[name]["rarity"] for name in mob_names]
    max_r     = max(rarities)
    weights   = [(2 ** (max_r + 1 - r)) for r in rarities]

    mob = random.choices(mob_names, weights=weights, k=1)[0]
    mob_path = f"assets/mobs/{mob}"
    try:
        if os.path.isdir(mob_path):
            imgs = [f for f in os.listdir(mob_path) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
            if not imgs:
                raise FileNotFoundError("No image files in directory")
            src = Image.open(os.path.join(mob_path, random.choice(imgs))).convert("RGBA")
        else:
            src = Image.open(f"{mob_path}.png").convert("RGBA")
    except FileNotFoundError:
        # still send an embed so UX is consistent
        pref = get_cached_prefix(chan.guild.id if chan.guild else None)
        e = discord.Embed(
            title="A mob is appearing!",
            description="(no image found this time) — say its name to catch it",
            color=discord.Color.blurple()
        )
        e.set_footer(text=f"For attribution & licensing, use {pref}credits")
        await chan.send(embed=e)
        return

    # ---- choose a focal point (same as before) ----
    alpha = src.split()[-1]
    bbox  = alpha.getbbox()
    if bbox:
        left, top, right, bottom = bbox
        found = False
        for _ in range(500):
            x = random.randint(left, right - 1)
            y = random.randint(top,  bottom - 1)
            if alpha.getpixel((x, y)) > 0:
                found = True
                break
        if not found:
            x = (left + right) // 2
            y = (top + bottom) // 2
        w, h = src.size
        center = (x / w, y / h)
    else:
        center = (random.uniform(0.1, 0.9), random.uniform(0.1, 0.9))

    # ---- frame creators (unchanged) ----
    def pixelate(img: Image.Image, size: int) -> Image.Image:
        small = img.resize((size, size), resample=Image.NEAREST)
        return small.resize(img.size, Image.NEAREST)

    def zoom_frame_at(src: Image.Image, zoom_frac: float, center_xy: tuple[float, float]) -> Image.Image:
        w, h = src.size
        f  = max(0.01, min(zoom_frac, 1.0))
        cw = int(w * f); ch = int(h * f)
        cx, cy = center_xy
        left = int(cx * w - cw / 2)
        top  = int(cy * h - ch / 2)
        left = max(0, min(left, w - cw))
        top  = max(0, min(top,  h - ch))
        crop = src.crop((left, top, left + cw, top + ch))
        return crop.resize((w, h), Image.NEAREST)

    pix = (random.randint(1, 4) == 1)
    frame_sizes = [1, 2, 4, 8, 16, src.size[0]]
    zoom_levels = [0.01, 0.05, 0.1, 0.2, 0.4, 1.0]
    levels     = frame_sizes if pix else zoom_levels
    make_frame = (lambda lvl: pixelate(src, lvl)) if pix else (lambda lvl: zoom_frame_at(src, lvl, center))

    # ---- build the embed once; image will be provided via attachment ----
    pref = get_cached_prefix(chan.guild.id if chan.guild else None)
    embed = discord.Embed(
        title="A mob is appearing!",
        description=f"Say its name to catch it.",
        color=discord.Color.blurple()
    )
    # IMPORTANT: point the embed image to the attachment filename
    embed.set_image(url="attachment://spawn.png")
    embed.set_footer(text=f"For attribution & licensing, use {pref}credits")

    # first frame
    buf = io.BytesIO()
    make_frame(levels[0]).save(buf, format="PNG")
    buf.seek(0)
    msg = await chan.send(
        embed=embed,
        file=discord.File(buf, "spawn.png")
    )

    # DB insert & expiry
    stay_seconds = RARITIES[MOBS[mob]["rarity"]]["stay"]
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=stay_seconds)

    async with bot.db_pool.acquire() as conn:
        rec = await conn.fetchrow(
            """
            INSERT INTO active_spawns
                (guild_id, channel_id, mob_name, message_id, revealed, spawn_time, expires_at)
            VALUES ($1,$2,$3,$4,0,$5,$6)
            RETURNING spawn_id
            """,
            chan.guild.id, chan.id, mob, msg.id, now, expires
        )

    # subsequent frames: replace the attachment, keep the same embed (it still points to attachment://spawn.png)
    for lvl in levels[1:]:
        await asyncio.sleep(15)
        buf = io.BytesIO()
        make_frame(lvl).save(buf, format="PNG")
        buf.seek(0)
        await msg.edit(
            embed=embed,
            attachments=[discord.File(buf, "spawn.png")]
        )

    # schedule expiry watcher
    bot.loop.create_task(
        watch_spawn_expiry(
            bot = bot,
            spawn_id=rec["spawn_id"],
            channel_id=chan.id,
            message_id=msg.id,
            mob_name=mob,
            expires_at=expires
        )
    )