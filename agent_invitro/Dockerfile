FROM python:3.11

WORKDIR /app

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

# 常駐HTTPサーバー化はしない（ADR-0019）。docker compose exec で ipython 接続する。
# メインプロセスとして sleep infinity を置き、コンテナを起動状態に維持する。
CMD ["sleep", "infinity"]
