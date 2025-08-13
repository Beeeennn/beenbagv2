import discord
import random
import asyncio
from constants import DISABLED_SHOP_ITEMS,MOBS
from utils.game_helpers import gid_from_ctx,give_mob,sucsac,gain_exp,give_items,giverole, get_items,take_items
from datetime import datetime,timedelta

async def shop(pool,ctx):
    """List all items you can buy in the shop (with some items hidden)."""
    disabled = [s.lower() for s in DISABLED_SHOP_ITEMS]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT item_id, name, description, price_emeralds, purchase_limit
            FROM shop_items
            WHERE NOT (lower(name) = ANY($1::text[]))  -- hide disabled items
            ORDER BY item_id
            """,
            disabled
        )

    embed = discord.Embed(title="🏪 Shop", color=discord.Color.gold())
    if not rows:
        embed.description = "No items for sale right now."
        return await ctx.send(embed=embed)

    for r in rows:
        limit = "unlimited" if r["purchase_limit"] is None else str(r["purchase_limit"])
        embed.add_field(
            name=f"{r['name']} — {r['price_emeralds']} 💠",
            value=f"{r['description']}\nLimit: {limit} per 24 h",
            inline=False
        )
    await ctx.send(embed=embed)

async def use(ctx, pool, bot, item_name, quantity):
    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    item_name = item_name.lower()

    if quantity <= 0:
        return await ctx.send("❌ Quantity must be greater than 0.")
    
    # allow "exp" shortcut for "Exp Bottle"
    if item_name in ("exp", "experience"):
        item_name = "exp bottle"
    elif item_name in ("pack", "mob pack", "mystery animal"):
        item_name = "mystery mob pack"
    elif item_name in ("boss ticket","ticket","mob ticket","boss mob"):
        item_name = "boss mob ticket"
    else:
        pass

    async with pool.acquire() as conn:
        # Check if they have it and it’s useable
        row = await conn.fetchrow("""
            SELECT quantity, useable
            FROM player_items
            WHERE player_id = $1 AND LOWER(item_name) = $2 AND guild_id = $3
        """, user_id, item_name,guild_id)

        if not row:
            return await ctx.send(f"❌ You don’t have any **{item_name}**.")
        if not row["useable"]:
            return await ctx.send(f"❌ **{item_name}** cannot be used.")
        if row["quantity"] < quantity:
            return await ctx.send(f"❌ You only have {row['quantity']} **{item_name}**.")
        if item_name == "fish food" and quantity%100 != 0:
            return await ctx.send(f"❌ You must put an amount of fish food divisible by 100.")
        # Deduct quantity or delete
        remaining = row["quantity"] - quantity
        if remaining > 0:
            await conn.execute("""
                UPDATE player_items
                SET quantity = $1
                WHERE player_id = $2 AND LOWER(item_name) = $3 AND guild_id = $4
            """, remaining, user_id, item_name,guild_id)
        else:
            await conn.execute("""
                DELETE FROM player_items
                WHERE player_id = $1 AND LOWER(item_name) = $2 AND guild_id = $3
            """, user_id, item_name,guild_id)
    # 🎉 Effect (optional)
    if item_name == "mystery mob pack":
        got = []
        mobs = ([m for m,v in MOBS.items() if not v["hostile"]])
        rarities = [MOBS[name]["rarity"] for name in mobs]
        max_r = max(rarities)
        weights = [(2**(max_r + 1-r)) for r in rarities]
        async with pool.acquire() as conn:      
            for _ in range(quantity): 
                is_golden = (random.randint(0,20)==16)             
                mobs = ([m for m,v in MOBS.items() if not v["hostile"]])
                mob = random.choices(mobs, weights=weights, k=1)[0]
                
                await conn.execute(
                    "INSERT INTO barn_upgrades (user_id,guild_id) VALUES ($1,$2) ON CONFLICT DO NOTHING;",
                    user_id,guild_id
                )
                # count current barn occupancy
                occ = await conn.fetchval(
                    "SELECT COALESCE(SUM(count),0) FROM barn WHERE user_id = $1 AND guild_id = $2",
                    user_id,guild_id
                )
                size = await conn.fetchval(
                    "SELECT barn_size FROM new_players WHERE user_id = $1 AND guild_id = $2",
                    user_id,guild_id
                )
                if occ >= size:
                    sac = True
                    reward = await sucsac(ctx.channel,ctx.author,mob,is_golden,"because the barn was too full",conn)
                    note = f"sacrificed for {reward} emeralds (barn is full)."
                    
                elif MOBS[mob]["hostile"]:
                    sac = True
                    reward = await sucsac(ctx.channel,ctx.author,mob,is_golden,"because the mob is hostile",conn)
                    note = f"this mob is not catchable so it was sacrificed for {reward} emeralds"
                else:
                    await give_mob(conn, user_id, mob,guild_id)
                    got.append(mob)
                await asyncio.sleep(1)
        # summarize what they got
        summary = {}
        for m in got:
            summary[m] = summary.get(m, 0) + 1
        lines = [f"**{cnt}× {name}**" for name,cnt in summary.items()]
        await ctx.send(f"Mystery pack used:\n" + "\n".join(lines))
    elif item_name == "exp bottle":
        async with pool.acquire() as conn:
            await gain_exp(conn,bot,user_id,quantity,None)
    elif item_name == "fish food":        
        emeralds_to_give = quantity // 100
        async with pool.acquire() as conn:
            await give_items(user_id, "emeralds", emeralds_to_give,"emeralds",False,conn,guild_id)
        await ctx.send(f"💠 You traded {quantity} fish food for {emeralds_to_give} emeralds!")
    elif item_name == "boss mob ticket":
        # ID of the user to ping (as a mention)
        special_user_id = 674671907626287151
        mention = f"<@{special_user_id}>"

        await ctx.send(f"🎫 You used a mob ticket! {mention}, a ticket has been claimed!")
        

    await ctx.send(f"✅ You used {quantity} **{item_name}**!")

async def buy(pool, ctx, args):
    """
    Purchase one or more of an item.
    Usage:
      !buy <item name> [quantity]
    Examples:
      !buy Exp Bottle 5
      !buy exp 100
    """
    if not args:
        return await ctx.send(f"❌ Usage: `{ctx.clean_prefix}buy <item name> [quantity]`")

    # 1) Parse quantity if last arg is an integer
    try:
        qty = int(args[-1])
        name_parts = args[:-1]
    except ValueError:
        qty = 1
        name_parts = args

    if qty < 1:
        return await ctx.send("❌ Quantity must be at least 1.")

    raw_name = " ".join(name_parts).strip().lower()

    # allow "exp" shortcut for "Exp Bottle"
    if raw_name in ("exp", "experience"):
        lookup_name = "exp bottle"
    elif raw_name in ("pack", "mob pack", "mystery mob pack"):
        lookup_name = "mystery animal"
    else:
        lookup_name = raw_name

    user_id = ctx.author.id
    guild_id = gid_from_ctx(ctx)
    async with pool.acquire() as conn:
        # 2) Look up the item
        item = await conn.fetchrow(
            """
            SELECT item_id, name, price_emeralds, purchase_limit
              FROM shop_items
             WHERE LOWER(name) = $1
            """,
            lookup_name
        )
        if not item:
            return await ctx.send(f"❌ No shop item named **{raw_name}**.")

        item_id      = item["item_id"]
        display_name = item["name"]
        cost_each    = item["price_emeralds"]
        limit        = item["purchase_limit"]  # None = unlimited

        total_cost = cost_each * qty

        # 3) Check emerald balance
        have = await get_items(conn,user_id,"emeralds",guild_id)

        if have < total_cost:
            return await ctx.send(
                f"❌ You need {total_cost} 💠 but only have {have}."
            )

        # 4) Enforce daily limit (for Exp Bottle only, or any limited item)
        if limit is not None:
            since = datetime.utcnow() - timedelta(hours=24)
            bought = await conn.fetchval(
                """
                SELECT COUNT(*) FROM purchase_history
                 WHERE user_id = $1
                   AND guild_id = $4
                   AND item_id = $2
                   AND purchased_at > $3
                """,
                user_id, item_id, since, guild_id
            )
            if bought + qty > limit:
                return await ctx.send(
                    f"❌ You can only buy {limit}/{limit} **{display_name}** per 24 h."
                )

        # 5) Deduct emeralds
        await take_items(user_id,"emeralds",total_cost,conn,guild_id)

        # 6) Log each purchase for history
        for _ in range(qty):
            await conn.execute(
                "INSERT INTO purchase_history (user_id, item_id, guild_id) VALUES ($1,$2,$3)",
                user_id, item_id, guild_id
            )
        # 7) Update your cumulative purchases (e.g. boss tickets)
        await conn.execute("""
            INSERT INTO shop_purchases (user_id,item_id,quantity,guild_id)
            VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id,item_id,guild_id) DO UPDATE
              SET quantity = shop_purchases.quantity + $3
        """, user_id, item_id, qty,guild_id)

    # 8) Grant the effect
    async with pool.acquire() as conn:
        if display_name == "Exp Bottle":
            await ctx.send(f"✅ Spent {total_cost} 💠 for an Exp Bottle with **{qty} EXP**! Say **!use Exp Bottle** to use them, you must use them all at once though")
            await give_items(user_id,"Exp Bottle",qty,"items",True,conn,guild_id)

        elif display_name == "Boss Mob Ticket":
            await ctx.send(
                f"✅ You bought **{qty} Boss Mob Ticket{'s' if qty!=1 else ''}**! "
                f"Use `{ctx.clean_prefix}use Ticket <mob name>` before stream to redeem, this allows you to say the name of the mob during the stream to spawn it, don't worry about typos, it will still be valid."
            )
            await give_items(user_id,"Boss Mob Ticket",qty,"items",True,conn,guild_id)

        elif display_name == "Mystery Animal":
            await ctx.send(
                f"✅ You bought **{qty} Mystery Mob Pack{'s' if qty!=1 else ''}**! "
                f"Use `{ctx.clean_prefix}use Mob Pack` to redeem"
            )
            await give_items(user_id,"Mystery Mob Pack",qty,"items",True,conn,guild_id)

        elif display_name == "RICH Role":
            await giverole(ctx,1396839599921168585,ctx.author)
            await ctx.send(f"✅ You bought **RICH role** for {total_cost} 💠!, you must be super rich. Be careful not to buy it again")
        else:
            await ctx.send(f"✅ You bought **{qty}× {display_name}** for {total_cost} 💠!")