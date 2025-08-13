# cogs/errors.py
import logging, traceback
from discord.ext import commands

log = logging.getLogger("beenbag.errors")

class ErrorSpy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # If the command or cog has its own handler, let that handle it (prevents duplicates)
        if hasattr(ctx.command, "on_error"):
            return
        if ctx.cog and ctx.cog._get_overridden_method(getattr(ctx.cog, "cog_command_error", None)):
            return

        err = getattr(error, "original", error)

        # --- Quietly ignore unknown commands for users (optional) ---
        if isinstance(err, commands.CommandNotFound):
            # Log useful diagnostics instead of sending a message
            log.warning(
                "CommandNotFound: %s | prefix=%r invoked_with=%r | author=%s(%s) | guild=%s | channel=%s | jump=%s",
                ctx.message.content,
                getattr(ctx, "prefix", None),
                getattr(ctx, "invoked_with", None),
                ctx.author, ctx.author.id,
                (ctx.guild and f"{ctx.guild.name}({ctx.guild.id})"),
                (getattr(ctx.channel, 'name', None) or ctx.channel.id),
                getattr(ctx.message, "jump_url", None),
            )
            # If you want full traceback (usually not needed for CommandNotFound):
            # log.debug("".join(traceback.format_exception(type(err), err, err.__traceback__)))
            return

        # --- Common friendly messages (optional) ---
        if isinstance(err, commands.MissingPermissions):
            await ctx.send("❌ You don’t have permission to do that.")
            return
        if isinstance(err, commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown. Try again in {int(err.retry_after)}s.")
            return

        # --- Fallback: log + one generic user message ---
        log.exception("Unhandled error in command %s", ctx.command, exc_info=err)
        try:
            await ctx.send(":boom: Something went wrong running that command.")
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorSpy(bot))
