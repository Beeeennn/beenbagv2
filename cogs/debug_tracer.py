# cogs/debug_tracer.py
import asyncio, inspect, logging, os, random, textwrap, traceback
from collections import defaultdict
from discord.ext import commands

log = logging.getLogger("beenbag.tracer")

INSTANCE_ID = os.getenv("RENDER_INSTANCE_ID") or hex(random.getrandbits(32))[2:8]

def _short_stack(skip=0, limit=12):
    frames = inspect.stack()[skip+1: skip+1+limit]
    out = []
    for f in frames:
        fn = os.path.basename(f.filename)
        out.append(f"{fn}:{f.lineno} in {f.function}")
    return " > ".join(out)

class DebugTracer(commands.Cog):
    """
    Shows WHERE commands are being run from.
    - Logs every on_message + command invocation with message.id
    - Logs every place that calls process_commands (stack trace!)
    - Tags all logs by INSTANCE_ID so you can spot multiple bot processes
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._orig_process_commands = bot.process_commands
        self._orig_invoke = bot.invoke
        # how many times a message has been processed this event-loop (by this process)
        self._msg_hits = defaultdict(int)

        # --- monkeypatch process_commands to log callers + stacks ---
        async def patched_process_commands(message):
            self._msg_hits[message.id] += 1
            call_no = self._msg_hits[message.id]
            stack = _short_stack(skip=1)  # caller of process_commands
            log.warning(
                "[%s] process_commands call #%d for msg %s by %s: %r | caller stack: %s",
                INSTANCE_ID, call_no, message.id, message.author, message.content, stack
            )
            try:
                return await self._orig_process_commands(message)
            except Exception:
                log.exception("[%s] Exception inside process_commands (msg %s)", INSTANCE_ID, message.id)
                raise

        async def patched_invoke(ctx: commands.Context):
            # log exactly which command object is about to run
            log.warning(
                "[%s] INVOKE %s (cmd=%s | cog=%s) msg_id=%s channel=%s guild=%s",
                INSTANCE_ID,
                getattr(ctx.command, "qualified_name", "?"),
                ctx.command, getattr(ctx.cog, "__class__", type("?", (), {})).__name__,
                ctx.message.id, ctx.channel, getattr(ctx.guild, "id", None),
            )
            return await self._orig_invoke(ctx)

        bot.process_commands = patched_process_commands  # type: ignore
        bot.invoke = patched_invoke                      # type: ignore

    @commands.Cog.listener()
    async def on_ready(self):
        log.warning("[%s] ONLINE as %s; cogs=%s", INSTANCE_ID, self.bot.user, list(self.bot.cogs.keys()))

    @commands.Cog.listener()
    async def on_message(self, message):
        # one line per message event this process receives
        # if you see two lines with the SAME msg.id but DIFFERENT INSTANCE_IDs -> 2 processes
        log.warning(
            "[%s] on_message msg_id=%s author=%s(%s) guild=%s content=%r",
            INSTANCE_ID, message.id, message.author, message.author.id,
            getattr(message.guild, "id", None), message.content
        )

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # don’t double-handle if a cog/command already has a handler
        if hasattr(ctx.command, "on_error"):
            log.warning("[%s] on_command_error skipped (per-command handler present) msg_id=%s cmd=%s",
                        INSTANCE_ID, ctx.message.id, ctx.command)
            return
        if ctx.cog and ctx.cog._get_overridden_method(getattr(ctx.cog, "cog_command_error", None)):
            log.warning("[%s] on_command_error skipped (cog handler present) msg_id=%s cmd=%s",
                        INSTANCE_ID, ctx.message.id, ctx.command)
            return

        err = getattr(error, "original", error)
        log.error(
            "[%s] COMMAND ERROR msg_id=%s cmd=%s content=%r\n%s",
            INSTANCE_ID, ctx.message.id, ctx.command, ctx.message.content,
            "".join(traceback.format_exception(type(err), err, err.__traceback__)),
        )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        log.warning(
            "[%s] COMPLETED %s msg_id=%s", INSTANCE_ID,
            getattr(ctx.command, "qualified_name", "?"), ctx.message.id
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(DebugTracer(bot))
