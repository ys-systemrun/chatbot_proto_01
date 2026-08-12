FROM python:3.11

WORKDIR /app

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

# シード元データ（CSV/JSON）をイメージに同梱する（ADR-0034）。
# AWS(ECS Fargate) にはローカルリポジトリの data/ をマウントする手段が無いため、
# ビルドコンテキスト内の data/ を、コードが参照する固定パス /data に焼き込む。
# （main.py は CSV_DATA_DIR="/" + os.environ["CSV_DATA_DIR"] とするため、
#  CSV_DATA_DIR=data → /data を読む。ローカルの docker-compose では ./data:/data の
#  ボリュームマウントがこの同梱データを上書きする＝差し替え運用は従来どおり可能。）
COPY data /data

# サーバー常駐ではなく、マイグレーション→シードを1回実行して終了するワンショット。
CMD ["python", "src/main.py"]
