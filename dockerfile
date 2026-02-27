# --- Stage 1: Build & Dependency Setup ---
FROM python:3.11-slim as builder

#old
# 2. Node.jsをインストールするための設定
# 最小限のパッケージ（curlなど）を入れ、Node.js 18以上をインストールします
#RUN apt-get update && apt-get install -y \
#    curl \
#    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
#    && apt-get install -y nodejs \
#    && apt-get clean \
#    && rm -rf /var/lib/apt/lists/*

# 2. OSパッケージと Node.js のインストール
# --no-install-recommends を使い、必要最小限のツールを堅実にインストールします
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 3. 作業ディレクトリの設定
WORKDIR /app

# 環境変数の設定（Pythonの書き込み最適化）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 4. 依存関係の定義ファイルを先にコピー（キャッシュ活用のため）
# package.json や requirements.txt がまだ空でもファイル自体は存在させておいてください
COPY package*.json ./
COPY requirements.txt ./

# 5. ライブラリのインストール
# requirements.txt をコピーしてインストール
# venvは使わず、システム領域にインストール（コンテナなのでOK）
RUN npm install && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. ソースコードのコピー
COPY . .

# 7. 実行コマンド
# 最初は bash を起動するようにしておくと、Dev Containers で入りやすいです
CMD ["bash"]