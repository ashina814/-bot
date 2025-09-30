from __future__ import annotations
import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# ---- 設定 ----
DATA_FILE = Path("omikuji_data.json")
TIMEZONE = ZoneInfo("Asia/Tokyo")

# 抽選の重み（合計100）
OMIKUJI_RESULTS = [
    ("大吉", 10),
    ("中吉", 20),
    ("小吉", 30),
    ("末吉", 25),
    ("凶", 10),
    ("大凶", 5),
]

# 大凶のときだけ付与される元
OMIKUJI_BAD_REWARD = 10000

# メッセージの候補
OMIKUJI_MESSAGES = [
    "春待つ心、今ぞ芽吹く",
    "水面に映る月、掴めぬは夢",
    "千里の道も一歩より始まる",
    "灯火は小さくとも闇を照らす",
    "鶴の声、遠く幸を告げる",
    "雲の切れ間に射す光あり",
    "落ち葉の舞いもまた道を示す",
    "石の上にも三年、忍ぶは力",
    "朝日昇れば、影は退く",
    "雨のち晴れ、また雨のち晴れ",
    "花は散れども、香りは残る",
    "行雲流水、心のままに",
]
# ----------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ファイルロック（async）
data_lock = asyncio.Lock()


async def load_data() -> dict:
    async with data_lock:
        if not DATA_FILE.exists():
            return {}
        try:
            text = DATA_FILE.read_text(encoding="utf-8")
            if not text:
                return {}
            return json.loads(text)
        except Exception as e:
            print("warning: failed to read data file:", e)
            return {}


async def save_data(data: dict) -> None:
    async with data_lock:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)


def today_str() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


async def ensure_user(data: dict, user_id: str) -> None:
    if user_id not in data:
        data[user_id] = {"last_omikuji": "", "元": 0}


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print("Failed to sync commands:", e)


@bot.tree.command(name="omikuji", description="今日のおみくじを引きます（1日1回）。")
async def omikuji(interaction: discord.Interaction):
    await interaction.response.defer()

    uid = str(interaction.user.id)
    data = await load_data()
    await ensure_user(data, uid)

    today = today_str()
    if data[uid].get("last_omikuji") == today:
        await interaction.followup.send(
            f"{interaction.user.mention} は今日すでにおみくじを引いています。明日またどうぞ。",
            ephemeral=True
        )
        return

    # 重み付き抽選
    names = [r[0] for r in OMIKUJI_RESULTS]
    weights = [r[1] for r in OMIKUJI_RESULTS]
    result = random.choices(names, weights=weights, k=1)[0]
    message = random.choice(OMIKUJI_MESSAGES)

    reward = 0
    if result == "大凶":
        reward = OMIKUJI_BAD_REWARD
        data[uid]["元"] = data[uid].get("元", 0) + reward

    data[uid]["last_omikuji"] = today
    await save_data(data)

    reply = f"{interaction.user.mention} のおみくじ — **{result}**\n『{message}』"
    if reward:
        reply += f"\n(特別に {reward}元 を付与しました)"

    await interaction.followup.send(reply)


# ---------------- Run ----------------
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")  # ← GitHubに載せても安全
    if not TOKEN:
        print("Error: 環境変数 DISCORD_TOKEN が設定されていません。")
    else:
        bot.run(TOKEN)
