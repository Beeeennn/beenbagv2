from utils.game_helpers import resolve_member, gid_from_ctx,sucsac
from constants import MOBS

async def c_givemob(pool, ctx, who, mob_name: str, count: int = 1):
    mob_name = mob_name.lower()
    member = await resolve_member(ctx, who)
    guild_id = gid_from_ctx(ctx)
    # Validate mob
    if mob_name.title() not in MOBS:
        return await ctx.send(f"❌ Mob `{mob_name}` not found.")
    
    # Validate count
    if count <= 0:
        return await ctx.send("❌ Count must be greater than 0.")
    
    async with pool.acquire() as conn:
        # 2) Fetch target’s barn capacity and current fill
        row = await conn.fetchrow(
            "SELECT barn_size FROM new_players_guild  WHERE user_id = $1 AND guild_id = $2",
            member.id, guild_id
        )
        target_size = row["barn_size"] if row else 5
        total_in_barn = await conn.fetchval(
            "SELECT COALESCE(SUM(count), 0) FROM barn WHERE user_id = $1 AND guild_id = $2",
            member.id, guild_id
        )
        if MOBS[mob_name.title()]["hostile"]:
            await sucsac(ctx,member,mob_name,False,"Because it cannot be captured",conn)
            return await ctx.send(f"✅ Sacrificed {mob_name} because it is hostile")

        if total_in_barn+count <= target_size:
            await conn.execute(
                """
                INSERT INTO barn (user_id, mob_name, is_golden, count, guild_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, mob_name, is_golden) DO UPDATE
                  SET count = barn.count + $4
                """,
                member.id, mob_name, False, count,guild_id
            )
    
            return await ctx.send(f"✅ Gave {count} × `{mob_name}` to {member.mention}.")
        else:
            return await ctx.send(f"✅ Could not give {count} × `{mob_name}` to {member.mention}, theres not enough space")

