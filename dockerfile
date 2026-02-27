# --- Stage 1: Build & Dependency Setup ---
FROM python:3.11-slim as builder

# 作業ディレクトリの設定
WORKDIR /app

# 環境変数の設定（Pythonの書き込み最適化）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 依存関係のインストール（ビルドツールが必要な場合のみ）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt をコピーしてインストール
# venvは使わず、システム領域にインストール（コンテナなのでOK）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim

WORKDIR /app

# builderステージからインストール済みパッケージをコピー
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# プロジェクトファイルをコピー
COPY . .

# MkDocs用のポート (8000) と RAG API用のポート (8080) を開けておく
EXPOSE 8000 8080

# デフォルトのコマンド（ここではMkDocsのサーバー起動を例に）
# RAG APIを動かす場合は uvicorn 等に変更
CMD ["mkdocs", "serve", "-a", "0.0.0.0:8000"]