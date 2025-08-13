# utils/permissions.py
import discord

# ----- User perms -----
def is_guild_admin(member: discord.Member) -> bool:
    """Treat Manage Guild OR Administrator as 'admin'."""
    if not isinstance(member, discord.Member):
        return False
    p = member.guild_permissions
    return p.administrator or p.manage_guild

def has_any_role(member: discord.Member, *role_ids: int) -> bool:
    """Check if the member has any of the given role IDs."""
    ids = set(role_ids)
    return any(r.id in ids for r in getattr(member, "roles", []))

# ----- Bot perms (targeted to a channel/thread) -----
def bot_perms_for(ctx) -> discord.Permissions:
    me = ctx.guild.me if ctx.guild else ctx.bot.user
    if hasattr(ctx.channel, "permissions_for"):
        return ctx.channel.permissions_for(me)
    return discord.Permissions.none()

def bot_can_send(ctx) -> bool:
    p = bot_perms_for(ctx)
    # threads use send_messages_in_threads; fall back to send_messages
    return p.view_channel and (getattr(p, "send_messages_in_threads", False) or p.send_messages)

def bot_can_react(ctx) -> bool:
    p = bot_perms_for(ctx)
    return p.view_channel and p.add_reactions

def bot_can_embed(ctx) -> bool:
    p = bot_perms_for(ctx)
    return bot_can_send(ctx) and p.embed_links

# ----- Friendly error text -----
def missing_perms_text(*perms: str) -> str:
    if not perms:
        return "I’m missing required permissions here."
    nice = ", ".join(p.replace("_", " ").title() for p in perms)
    return f"I’m missing: **{nice}** in this channel."
