from __future__ import annotations
import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import threading

import discord
from discord.ext import commands
# Koyebのヘルスチェックに対応するためのWebサーバー機能
from fastapi import FastAPI
import uvicorn

# ---- 設定 ----
# Koyebで永続ボリュームを設定しない場合は、データは再起動時に消えます
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
# コマンドのプレフィックスは '!'
bot = commands.Bot(command_prefix="!", intents=intents)

# ファイルロック（非同期処理でのデータ競合を防ぐ）
data_lock = asyncio.Lock()


async def load_data() -> dict:
    """JSONファイルからユーザーデータを非同期で読み込む"""
    async with data_lock:
        if not DATA_FILE.exists():
            return {}
        try:
            text = DATA_FILE.read_text(encoding="utf-8")
            if not text:
                return {}
            # JSON文字列をPythonの辞書に変換
            return json.loads(text)
        except Exception as e:
            # 読み込み失敗時は警告を出し、空の辞書を返す
            print("warning: failed to read data file:", e)
            return {}


async def save_data(data: dict) -> None:
    """ユーザーデータを非同期でJSONファイルに書き込む（アトミックな書き込み）"""
    async with data_lock:
        # 一時ファイルに書き込み、成功後にリネームすることで、書き込み途中の破損を防ぐ
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)


def today_str() -> str:
    """現在の日付を 'YYYY-MM-DD' 形式で東京タイムゾーンで取得する"""
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")


async def ensure_user(data: dict, user_id: str) -> None:
    """ユーザーデータが存在しない場合に初期化する"""
    if user_id not in data:
        data[user_id] = {"last_omikuji": "", "元": 0}


@bot.event
async def on_ready():
    """BotがDiscordにログイン完了したときに実行される"""
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        # スラッシュコマンドをDiscordに同期
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print("Failed to sync commands:", e)


@bot.tree.command(name="omikuji", description="今日のおみくじを引きます（1日1回）。")
async def omikuji(interaction: discord.Interaction):
    """おみくじコマンドの処理"""
    # 処理に時間がかかるため、応答を遅延させる
    await interaction.response.defer()

    uid = str(interaction.user.id)
    data = await load_data()
    await ensure_user(data, uid)

    today = today_str()
    # 本日既におみくじを引いているかチェック
    if data[uid].get("last_omikuji") == today:
        await interaction.followup.send(
            f"{interaction.user.mention} は今日すでにおみくじを引いています。明日またどうぞ。",
            # ephemeral=True でメッセージを引いた本人にしか見えないようにする
            ephemeral=True 
        )
        return

    # 重み付き抽選の実行
    names = [r[0] for r in OMIKUJI_RESULTS]
    weights = [r[1] for r in OMIKUJI_RESULTS]
    result = random.choices(names, weights=weights, k=1)[0]
    message = random.choice(OMIKUJI_MESSAGES)

    reward = 0
    if result == "大凶":
        # 大凶の場合のみ、特別報酬を付与
        reward = OMIKUJI_BAD_REWARD
        data[uid]["元"] = data[uid].get("元", 0) + reward

    # データ更新
    data[uid]["last_omikuji"] = today
    await save_data(data)

    # 応答メッセージの作成と送信
    reply = f"{interaction.user.mention} のおみくじ — **{result}**\n『{message}』"
    if reward:
        reply += f"\n(特別に {reward}元 を付与しました)"

    await interaction.followup.send(reply)


# ---------------- Koyeb ヘルスチェック対策 ----------------

def start_server():
    """Botとは別のスレッドでWebサーバーを起動する"""
    # サーバーインスタンスを作成
    app = FastAPI()

    @app.get("/")
    def read_root():
        # Koyebのヘルスチェックがこのエンドポイントを叩きます
        return {"status": "Bot is Running", "discord_user": str(bot.user)}

    # uvicornを使ってサーバーを0.0.0.0:8080で起動
    # Koyebのデフォルトポートは8080です
    uvicorn.run(app, host="0.0.0.0", port=8080)


# ---------------- Botの起動 ----------------
if __name__ == "__main__":
    # 環境変数からトークンを取得。ローカルやKoyebで安全に実行するために必須。
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    if not TOKEN:
        print("Error: 環境変数 DISCORD_TOKEN が設定されていません。Botを終了します。")
    else:
        # 1. Webサーバーを別スレッドで起動する (Koyeb対策)
        server_thread = threading.Thread(target=start_server)
        server_thread.daemon = True # メインスレッド終了時に一緒に終了させる
        server_thread.start()
        
        # 2. Discord Botをメインスレッドで起動する
        print("Starting Discord Bot...")
        bot.run(TOKEN)
