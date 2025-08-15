# core/decorators.py
from discord.ext import commands
from services.monetization import peek_premium

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