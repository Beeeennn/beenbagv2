import discord
from constants import MOBS, RARITIES
from utils.game_helpers import take_items,gid_from_ctx,get_items,resolve_member,sucsac,ensure_player,give_mob


async def sac(pool, ctx, mob_name: str):
    """
    Sacrifice one mob from your barn for emeralds based on rarity.
    Usage: !sacrifice <mob name>
    """
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    key = mob_name.title()
    # Check for special @beennn sacrifice case
    if mob_name.lower() in ("@beeeenjaminnn", "<@674671907626287151>", "been","beenn"):  # replace with their real user ID
        async with pool.acquire() as conn:
            diamond_count = await get_items(conn, user_id, "diamond",guild_id)
            if diamond_count == 0:
                return await ctx.send("💎 You don’t even have a diamond to take **L**.")
            
            # Remove one diamond
            await take_items(user_id, "diamond", 1, conn,guild_id)
            await ctx.send(f"💀 You were a fool to think you could sacrifice Beenn, he beat you in combat and took a diamond.")
            return
    # validate mob
    if key not in MOBS:
        return await ctx.send(f"❌ I don’t recognize **{mob_name}**.")
    rarity = MOBS[key]["rarity"]
    rar_info = RARITIES[rarity]
    reward  = rar_info["emeralds"]
    async with pool.acquire() as conn:
        # check barn
        rec = await conn.fetchrow(
            """
            SELECT count, is_golden
              FROM barn
             WHERE user_id=$1 AND mob_name=$2 AND guild_id = $3
             ORDER BY is_golden DESC
             LIMIT 1
            """,
            user_id, key, guild_id
        )

        if not rec:
            return await ctx.send(f"❌ You have no **{key}** to sacrifice.")
        have     = rec["count"]
        is_gold  = rec["is_golden"]
        if have > 1:
            await conn.execute(
                "UPDATE barn SET count = count - 1 WHERE user_id=$1 AND guild_id = $2 AND mob_name=$3",
                user_id, guild_id, key
            )
        else:
            await conn.execute(
                "DELETE FROM barn WHERE user_id=$1 AND guild_id = $2 AND mob_name = $3",
                user_id, guild_id, key
            )
        await sucsac(ctx,ctx.author,mob_name,is_gold,"",conn)

async def bestiary(pool, ctx, who: str = None):
    """Show all mobs you’ve sacrificed, split by Golden vs. normal and by rarity."""
    guild_id = gid_from_ctx(ctx)
    # Resolve who → Member (or fallback to author)
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")  # or "Member not found."

    # Now you’ve got a real Member with .id, .display_name, etc.
    user_id = member.id
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT mob_name, is_golden, rarity, COUNT(*) AS cnt
              FROM sacrifice_history
             WHERE discord_id = $1 AND guild_id = $2
             GROUP BY is_golden, rarity, mob_name
             ORDER BY is_golden DESC, rarity ASC, mob_name
            """,
            user_id,guild_id
        )

    # organize: data[gold_flag][rarity] = [(mob, cnt), ...]
    data = {True: {}, False: {}}
    for r in rows:
        g = r["is_golden"]
        rar = r["rarity"]
        data[g].setdefault(rar, []).append((r["mob_name"], r["cnt"]))

    embed = discord.Embed(
        title=f"{member.display_name}'s Sacrifice Bestiary",
        color=discord.Color.teal()
    )

    def add_section(gold_flag, title):
        section = data[gold_flag]
        if not section:
            return
        # header for this group
        embed.add_field(name=title, value="​", inline=False)
        for rar in sorted(section):
            info = RARITIES[rar]
            label = f"{info['name'].title()} [{rar}]"
            lines = [f"• **{name}** × {cnt}" for name, cnt in section[rar]]
            embed.add_field(name=label, value="\n".join(lines), inline=False)

    # golden first
    add_section(True, "✨ Golden Sacrificed Mobs ✨")
    # then normal
    add_section(False, "Sacrificed Mobs")

    await ctx.send(embed=embed)

async def breed(pool, ctx, mob: str):
    """Breed a mob (costs wheat & requires 2 in your barn)."""
    user_id = ctx.author.id
    key     = mob.title()

    # 1) Validate mob exists and is non-hostile
    if key not in MOBS:
        return await ctx.send(f"❌ `{mob}` isn’t a valid mob.")
    if MOBS[key]["hostile"]:
        return await ctx.send(f"❌ You can’t breed a hostile mob like **{key}**.")
    
    wheat = RARITIES[MOBS[key]["rarity"]]["wheat"]
    guild_id = gid_from_ctx(ctx)
    async with pool.acquire() as conn:
        await ensure_player(conn, user_id,guild_id)

        # 2) Check wheat balance
        wheat_have = await get_items(conn, user_id, "wheat",guild_id)
        if wheat_have < wheat:
            return await ctx.send(
                f"❌ You need **{wheat} wheat** to breed, but only have **{wheat_have}**."
            )

        # 3) Check barn count for that mob (non-golden)
        have = await conn.fetchval(
            """
            SELECT count
              FROM barn
             WHERE user_id=$1 AND guild_id = $2 AND mob_name=$3 AND is_golden=false
            """,
            user_id, guild_id, key
        ) or 0
        if have < 2:
            return await ctx.send(
                f"❌ You need at least **2** **{key}** in your barn to breed, but only have **{have}**."
            )

        # 4) Check barn space
        occupancy = await conn.fetchval(
            "SELECT COALESCE(SUM(count), 0) FROM barn WHERE user_id = $1 AND guild_id = $2",
            user_id,guild_id
        )
        barn_size = await conn.fetchval(
            "SELECT barn_size FROM new_players WHERE user_id = $1 AND guild_id = $2",
            user_id,guild_id
        )
        if occupancy >= barn_size:
            return await ctx.send(
                f"❌ Your barn is full (**{occupancy}/{barn_size}**). Upgrade it before breeding more mobs!"
            )

        # 5) Deduct wheat and breed
        await take_items(user_id, "wheat", wheat, conn,guild_id)
        new_count = await give_mob(conn, user_id, key,guild_id)

    # 6) Success
    await ctx.send(
        f"🐣 {ctx.author.mention} bred a **{key}**! "
        f"You now have **{new_count}** **{key}** in your barn."
    )


async def give(pool, ctx, who: str, mob: str):
    member = await resolve_member(ctx, who)
    if not member:
        return await ctx.send("There is no user with this name")
    if member.id == ctx.author.id:
        return await ctx.send("❌ You can’t give to yourself.")

    mob_name = mob.title()
    if mob_name not in MOBS:
        return await ctx.send(f"❌ `{mob_name}` isn’t a known mob.")

    giver_id   = ctx.author.id
    target_id  = member.id
    g          = ctx.guild.id

    async with pool.acquire() as conn:
        # Target barn capacity + current fill (per guild)
        row = await conn.fetchrow(
            "SELECT barn_size FROM new_players WHERE guild_id=$1 AND user_id=$2",
            g, target_id
        )
        target_size = row["barn_size"] if row else 5

        total_in_barn = await conn.fetchval(
            "SELECT COALESCE(SUM(count), 0) FROM barn WHERE guild_id=$1 AND user_id=$2",
            g, target_id
        )

        # Take one mob from giver (prefer non-golden)
        rec = await conn.fetchrow(
            """
            SELECT is_golden, count
              FROM barn
             WHERE guild_id=$1 AND user_id=$2 AND mob_name=$3
             ORDER BY is_golden ASC
             LIMIT 1
            """,
            g, giver_id, mob_name
        )
        if not rec:
            return await ctx.send(f"❌ You have no **{mob_name}** to give.")
        is_golden = rec["is_golden"]
        have      = rec["count"]

        if have > 1:
            await conn.execute(
                """
                UPDATE barn
                   SET count = count - 1
                 WHERE guild_id=$1 AND user_id=$2 AND mob_name=$3 AND is_golden=$4
                """,
                g, giver_id, mob_name, is_golden
            )
        else:
            await conn.execute(
                """
                DELETE FROM barn
                 WHERE guild_id=$1 AND user_id=$2 AND mob_name=$3 AND is_golden=$4
                """,
                g, giver_id, mob_name, is_golden
            )

        # If recipient has room, transfer it
        if total_in_barn < target_size:
            await conn.execute(
                """
                INSERT INTO barn (guild_id, user_id, mob_name, is_golden, count)
                VALUES ($1, $2, $3, $4, 1)
                ON CONFLICT (guild_id, user_id, mob_name, is_golden)
                DO UPDATE SET count = barn.count + 1
                """,
                g, target_id, mob_name, is_golden
            )
            return await ctx.send(
                f"✅ You gave {'✨ ' if is_golden else ''}**{mob_name}** to {member.mention}!"
            )

        # Else, sacrifice it for emeralds to the **giver**
        rarity = MOBS[mob_name]["rarity"]
        base   = RARITIES[rarity]["emeralds"]
        reward = base * (2 if is_golden else 1)

        # sucsac already handles granting emeralds & embed; make sure it’s guild-aware if needed
        await sucsac(ctx, ctx.author, mob_name, is_golden, f"because {member.display_name}'s barn was full", conn)

    await ctx.send(
        f"⚠️ {member.display_name}`s barn is full, so you sacrificed "
        f"{'✨ ' if is_golden else ''}**{mob_name}** for 💠 **{reward}** emeralds!"
    )
async def barn(pool, ctx, who: str = None):
    """Show your barn split by Golden vs. normal and by rarity."""
    # Resolve who → Member (or fallback to author)
    
    if who is None:
        member = ctx.author
    else:
        member = await resolve_member(ctx, who)
        if member is None:
            return await ctx.send("Member not found.")  # or "Member not found."

    # Now you’ve got a real Member with .id, .display_name, etc.
    user_id = member.id
    guild_id = gid_from_ctx(ctx)
    # 1) Fetch barn entries
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT mob_name, is_golden, count
              FROM barn
             WHERE user_id = $1 AND count > 0 AND guild_id = $2
             ORDER BY is_golden DESC, mob_name
            """,
            user_id,guild_id
        )
        if not rows:
            return await ctx.send(embed=discord.Embed(
                title=f"{member.display_name}'s Barn (0/{size} slots)",
                description="No mobs yet. Go catch some!",
                color=discord.Color.green()
            ))

        # fetch barn size & next upgrade cost if you still want those
        size_row = await conn.fetchrow(
            "SELECT barn_size FROM new_players WHERE user_id = $1 AND guild_id = $2", user_id, guild_id
        )
        size = size_row["barn_size"] if size_row else 5

        # 2) Organize by gold flag → rarity → list of (mob, count)
        data = {True: {}, False: {}}
        for r in rows:
            g    = r["is_golden"]
            name = r["mob_name"]
            cnt  = r["count"]
            rar  = MOBS[name]["rarity"]
            data[g].setdefault(rar, []).append((name, cnt))

        # 3) Build embed
        occ = await conn.fetchval(
            "SELECT COALESCE(SUM(count),0) FROM barn WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id
        )
    embed = discord.Embed(
        title=f"{member.display_name}'s Barn ({occ}/{size} slots)",
        color=discord.Color.green()
    )
    embed.set_footer(text="Use !upbarn to expand your barn.")

    def add_section(is_gold: bool, header: str):
        section = data[is_gold]
        if not section:
            return
        # Section header
        embed.add_field(name=header, value="​", inline=False)
        # For each rarity in ascending order
        for rar in sorted(section):
            info = RARITIES[rar]
            # e.g. “Common [1]”
            field_name = f"{info['name'].title()} [{rar}]"
            lines = [
                f"• **{n}** × {c}"
                for n, c in section[rar]
            ]
            embed.add_field(
                name=field_name,
                value="\n".join(lines),
                inline=False
            )

    # 4) Golden first, then normal
    add_section(True,  "✨ Golden Mobs ✨")
    add_section(False, "Mobs")

    await ctx.send(embed=embed)

async def upbarn(pool, ctx):
    """Upgrades your barn by +1 slot, costing (upgrades + 1) wood."""
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    async with pool.acquire() as conn:
        await ensure_player(conn,user_id,guild_id)
        # 2) Ensure barn_upgrades row exists
        await conn.execute(
            "INSERT INTO barn_upgrades (user_id, guild_id) VALUES ($1,$2) ON CONFLICT DO NOTHING;",
            user_id,guild_id
        )

        # 3) Get how many times they’ve upgraded
        up = await conn.fetchrow(
            "SELECT times_upgraded FROM barn_upgrades WHERE user_id = $1 AND guild_id = $2",
            user_id,guild_id
        )
        times_upgraded = up["times_upgraded"]

        # 4) Compute next upgrade cost
        next_cost = (times_upgraded + 1) * 3

        # 5) Check they have enough wood
        pl = await conn.fetchrow(
            "SELECT barn_size FROM new_players WHERE user_id = $1 AND guild_id = $2",
            user_id,guild_id
        )
        current_size = pl["barn_size"]

        player_wood = await get_items(conn, user_id, "wood",guild_id)

        if player_wood < next_cost:
            return await ctx.send(
                f"{ctx.author.mention} you need **{next_cost} wood** to upgrade your barn, "
                f"but you only have **{player_wood} wood**."
            )

        # 6) Perform the upgrade
        await take_items(user_id,"wood",next_cost,conn,guild_id)
        await conn.execute(
            """
            UPDATE barn_upgrades
               SET times_upgraded = times_upgraded + 1
             WHERE user_id = $1 AND guild_id = $2
            """,
            user_id,guild_id
        )

        await conn.fetchrow(
            "UPDATE new_players SET barn_size = barn_size+1 WHERE user_id = $1 AND guild_id=$2",
            user_id,guild_id
        )
        # 7) Fetch post‐upgrade values
        row = await conn.fetchrow(
            "SELECT barn_size FROM new_players WHERE user_id = $1 AND guild_id = $2",
            user_id,guild_id
        )

        new_wood = await get_items(conn, user_id, "wood",guild_id)
        new_size = row["barn_size"]

    # 8) Report back
    await ctx.send(
        f"{ctx.author.mention} upgraded their barn from **{current_size}** to **{new_size}** slots "
        f"for 🌳 **{next_cost} wood**! You now have **{new_wood} wood**."
    )
