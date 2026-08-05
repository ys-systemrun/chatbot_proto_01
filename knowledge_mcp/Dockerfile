FROM python:3.11

WORKDIR /app

# curl は docker-compose の healthcheck（/health への疎通確認）で使用する
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

EXPOSE 8100

CMD ["python", "-m", "knowledge_mcp.main"]
