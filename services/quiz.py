from discord.ext import commands
import discord, asyncio, random, re
from pathlib import Path
from services import achievements
from utils import game_helpers

# Put this inside your Cog class
async def quiz(db_pool, ctx: commands.Context, rounds: int = 5, file_path: str = "assets\quiz_questions.txt"):
    import random, asyncio, re, time
    from pathlib import Path
    import discord

    def _split_unescaped_pipes(line: str) -> list[str]:
        return [p.replace(r'\|', '|').strip() for p in re.split(r'(?<!\\)\|', line)]

    def load_questions(path: Path):
        qs = []
        with path.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = _split_unescaped_pipes(line)
                if len(parts) != 6:
                    continue
                q, a, b, c, d, correct = parts
                correct = correct.upper()
                if correct not in ("A", "B", "C", "D"):
                    continue
                qs.append({"q": q, "choices": {"A": a, "B": b, "C": c, "D": d}, "answer": correct})
        return qs

    # ---- load questions ----
    try:
        all_qs = load_questions(Path(file_path))
    except Exception as e:
        return await ctx.send(f"⚠️ {e}")
    if not all_qs:
        return await ctx.send("⚠️ No valid questions found.")

    rounds = min(rounds, len(all_qs))
    pool = random.sample(all_qs, rounds)

    A, B, C, D = "🇦", "🇧", "🇨", "🇩"
    reverse_map = {A: "A", B: "B", C: "C", D: "D"}

    scores: dict[int, int] = {}
    fast_users: list[int] = []   # users who answered any question <1s
    firsts_per_q: list[int] = [] # user_id who was first for each question

    # ---- intro frame (15s) ----
    intro = discord.Embed(
        title="⛏️ Trivia Villager is setting up questions…",
        description="Answer them quickly to get **emeralds**!\nEveryone can answer!!!\nThink carefully, he only acceps your first answer\n\n⏳ Starting in 15 seconds…",
        color=discord.Color.green(),
    )
    await ctx.send(embed=intro)
    await asyncio.sleep(15)

    # ---- quiz rounds ----
    for i, item in enumerate(pool, 1):
        ans = item["answer"]
        embed = discord.Embed(
            title=f"Question {i}/{rounds}",
            description=(
                f"{item['q']}\n\n"
                f"{A} **A)** {item['choices']['A']}\n"
                f"{B} **B)** {item['choices']['B']}\n"
                f"{C} **C)** {item['choices']['C']}\n"
                f"{D} **D)** {item['choices']['D']}\n"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="15s to answer! First 3 correct get emeralds. Wrong answers = out this round.")
        msg = await ctx.send(embed=embed)
        for em in (A, B, C, D):
            try:
                await msg.add_reaction(em)
            except:
                pass

        correct_users: list[discord.User] = []  # order matters
        disqualified: set[int] = set()
        start_time = time.perf_counter()

        def check(reaction: discord.Reaction, user: discord.User):
            if reaction.message.id != msg.id or user.bot:
                return False
            choice = reverse_map.get(str(reaction.emoji))
            if not choice:
                return False
            if user.id in disqualified or any(u.id == user.id for u in correct_users):
                return False
            if choice != ans:  # wrong -> DQ
                disqualified.add(user.id)
                return False
            return True

        try:
            while len(correct_users) < 3:
                reaction, user = await ctx.bot.wait_for("reaction_add", timeout=15.0, check=check)
                elapsed = time.perf_counter() - start_time
                correct_users.append(user)
                if elapsed < 0.5:
                    fast_users.append(user.id)
                if len(correct_users) == 1:
                    firsts_per_q.append(user.id)
        except asyncio.TimeoutError:
            pass

        # award emeralds
        for idx, user in enumerate(correct_users):
            pts = 3 - idx
            scores[user.id] = scores.get(user.id, 0) + pts

        # --- Results screen (10s) ---
        def name_for(u: discord.User | int) -> str:
            if isinstance(u, int):
                m = ctx.guild.get_member(u) if ctx.guild else None
                return m.display_name if m else f"<@{u}>"
            else:
                m = ctx.guild.get_member(u.id) if ctx.guild else None
                return m.display_name if m else f"<@{u.id}>"

        podium = [name_for(u) for u in correct_users] + ["—"] * (3 - len(correct_users))

        result_embed = discord.Embed(
            title=f"📣 Round {i} Results",
            description=(
                f"**Question:** {item['q']}\n"
                f"**Correct Answer:** {ans}) {item['choices'][ans]}\n\n"
                f"🥇 {podium[0]}  (+3)\n"
                f"🥈 {podium[1]}  (+2)\n"
                f"🥉 {podium[2]}  (+1)\n\n"
                f"Showing for **10 seconds**…"
            ),
            color=discord.Color.green(),
        )
        await ctx.send(embed=result_embed)
        await asyncio.sleep(10)

    # ---- final leaderboard ----
    gid = game_helpers.gid_from_ctx(ctx)
    if scores:
        def display_name(uid: int) -> str:
            m = ctx.guild.get_member(uid) if ctx.guild else None
            return m.display_name if m else f"<@{uid}>"

        lines = []
        async with db_pool.acquire() as conn:
            for uid, pts in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"**{display_name(uid)}** — {pts} emerald{'s' if pts != 1 else ''}")
                await game_helpers.give_items(uid,"emeralds",pts,"emeralds",False,conn,gid)

        lb = discord.Embed(
            title="🏆 Final Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=lb)

        # logs
        for uid in set(fast_users):
            await achievements.try_grant(db_pool,ctx,uid,"fast_quiz")
        for uid in set(firsts_per_q):
            if firsts_per_q.count(uid) == rounds:
                await achievements.try_grant(db_pool,ctx,uid,"full_marks")
    else:
        await ctx.send("No emeralds were earned this time.")
