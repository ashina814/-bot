# 1. ベースイメージの選択: Pythonの軽量版
# Botが使用するPythonのバージョンに合わせてください
FROM python:3.11-slim

#　2. 作業ディレクトリの設定
WORKDIR /app

# 3. 依存関係のインストール
# requirements.txtを先にコピー
COPY requirements.txt .

# 依存関係をインストール
# 【重要】Botに必要な全てのライブラリ（discord.py, zoneinfo, python-dotenvなど）が
#         この requirements.txt に記述されていることを確認してください！
RUN pip install --no-cache-dir -r requirements.txt

# 4. アプリケーションコードのコピー
# Botのコードやデータファイル（omikuji_data.json）をコピー
COPY . .

#　5. 起動コマンドの設定
# 【重要】あなたのメインファイル名に合わせてください
# もしこのファイルが `main.py` なら、このままでOKです。
CMD [ "python", "御神籤.py" ]　
