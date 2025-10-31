FROM python:3.11-slim

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# staticfilesディレクトリを作成（collectstatic用）
RUN mkdir -p /app/staticfiles

EXPOSE 8000