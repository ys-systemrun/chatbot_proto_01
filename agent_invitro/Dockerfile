FROM python:3.11

WORKDIR /app

# curl は AWS 環境の ECS コンテナヘルスチェック（/health への疎通確認, IMPL-202608241104 T27）で使用する。
# knowledge_mcp / tag_selector_mcp の Dockerfile と同形式。ローカル docker-compose（sleep infinity）
# では未使用だが、イメージは共通のため同梱する。
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

# 常駐HTTPサーバー化はしない（ADR-0019）。docker compose exec で ipython 接続する。
# メインプロセスとして sleep infinity を置き、コンテナを起動状態に維持する。
CMD ["sleep", "infinity"]
