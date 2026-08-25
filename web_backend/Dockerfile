FROM python:3.11

WORKDIR /app

# COPY requirements.txt .
# RUN pip install -r requirements.txt

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

# エントリポイントを明示（自動探索に依存しない）。ルート定義は src/main/app.py に集約。
CMD ["fastapi", "dev", "src/main/app.py", "--host", "0.0.0.0"]
# CMD ["fastapi", "dev", "src/main/app.py", "--host", "0.0.0.0", "--port", "8000"]