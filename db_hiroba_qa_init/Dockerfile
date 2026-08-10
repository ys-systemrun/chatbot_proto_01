FROM python:3.11

WORKDIR /app

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

# サーバー常駐ではなく、マイグレーション→シードを1回実行して終了するワンショット。
CMD ["python", "src/main.py"]
