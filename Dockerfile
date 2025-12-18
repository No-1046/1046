FROM python:3.11-slim

# 【重要】ビルドに必要なツールを追加インストール
# build-essential: gcc/g++などのコンパイラ (llama_cpp_pythonに必須)
# cmake: ビルドシステム (llama_cpp_pythonに必須)
# libgomp1: LightGBMに必須
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/

# pip自体を最新にしておくことでビルド成功率が上がります
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY . /app

# ★注意★ "myproject" の部分は、あなたの実際のDjangoプロジェクト名（フォルダ名）に書き換えてください
# 例: "mysite.wsgi:application" や "config.wsgi:application" など
CMD ["gunicorn", "myproject.wsgi:application", "--bind", "0.0.0.0:8000"]