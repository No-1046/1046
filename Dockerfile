FROM python:3.11-slim

# LightGBMに必要なライブラリを追加
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/


RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

COPY . /app
CMD ["gunicorn", "myproject.wsgi:application", "--bind", "0.0.0.0:8000"]
