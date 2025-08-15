# core/decorators.py
from discord.ext import commands
from services.monetization import peek_premium
import math
def premium_cooldown(rate: int, per: float, bucket: commands.BucketType = commands.BucketType.member):
    def factory(ctx) -> commands.Cooldown:
        is_premium = peek_premium(ctx.author.id)  # sync, fast, no await
        effective_per = per * 0.8 if is_premium else per
        return commands.Cooldown(rate, effective_per)

    deco = commands.dynamic_cooldown(factory, bucket)

    def wrapper(func):
        cmd = deco(func)
        cmd.extras = getattr(cmd, "extras", {})
        cmd.extras["base_cooldown"] = {"rate": rate, "per": per, "bucket": bucket.name.lower()}
        cmd.extras["premium_modifier"] = "20% shorter (global)"
        return cmd

    return wrapper


def premium_fixed_cooldown(
    *,
    free_seconds: int,
    premium_seconds: int,
    bucket: commands.BucketType = commands.BucketType.member
):
    """Premium users get a fixed cooldown; free users get a longer one."""
    def factory(ctx) -> commands.Cooldown:
        is_premium = peek_premium(ctx.author.id)
        per = premium_seconds if is_premium else free_seconds
        return commands.Cooldown(1, per)

    deco = commands.dynamic_cooldown(factory, bucket)

    def wrapper(func):
        cmd = deco(func)
        cmd.extras = getattr(cmd, "extras", {})
        cmd.extras["cooldown_policy"] = {
            "premium_seconds": premium_seconds,
            "free_seconds": free_seconds,
            "bucket": bucket.name.lower(),
        }
        return cmd

    return wrapper

async def send_premium_cooldown_message(ctx, error: commands.CommandOnCooldown):
    seconds = math.ceil(error.retry_after)
    m, s = divmod(seconds, 60)
    parts = []
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    wait_str = " ".join(parts)
    await ctx.send(
        f"⏳ You need to wait **{wait_str}** to do this again.\n"
        f"Get **Premium** to reduce this cooldown! 'premium'"
    )
