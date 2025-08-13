# tasks/fish_food.py
import asyncio
import logging

async def give_fish_food_task(bot, db_pool):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with db_pool.acquire() as conn:
                # 0) Prune fish older than 24h
                await conn.execute("""
                    DELETE FROM aquarium
                    WHERE time_caught < NOW() - INTERVAL '1 day'
                """)

                # 1) Compute per (guild,user) uniqueness over most recent 30 fish
                #    and upsert that amount of "fish food" in one statement.
                #    NOTE: if you want each tick to grant exactly the uniqueness count,
                #    this adds that per tick. That's your current design.
                await conn.execute("""
                    WITH ranked AS (
                        SELECT guild_id, user_id, color1, color2, type,
                               ROW_NUMBER() OVER (
                                   PARTITION BY user_id, guild_id
                                   ORDER BY time_caught DESC
                               ) AS rn
                        FROM aquarium
                    ),
                    limited AS (
                        SELECT guild_id, user_id, color1, color2, type
                        FROM ranked
                        WHERE rn <= 30
                    ),
                    agg AS (
                        SELECT guild_id,
                               user_id,
                               COUNT(DISTINCT color1)
                             + COUNT(DISTINCT color2)
                             + COUNT(DISTINCT type) AS qty
                        FROM limited
                        GROUP BY guild_id, user_id
                        HAVING COUNT(*) > 0
                    )
                    INSERT INTO player_items (guild_id, player_id, item_name, category, quantity, useable)
                    SELECT guild_id, user_id, 'fish food', 'resource', qty, TRUE
                    FROM agg
                    ON CONFLICT (guild_id, player_id, item_name)
                    DO UPDATE SET quantity = player_items.quantity + EXCLUDED.quantity;
                """)
            logging.info("✅ Fish food distributed.")
        except Exception as e:
            logging.exception("Fish food task failed: %s", e)

        await asyncio.sleep(1800)  # 30 minutes
