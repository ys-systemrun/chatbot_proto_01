FROM python:3.11

WORKDIR /app

# COPY requirements.txt .
# RUN pip install -r requirements.txt

COPY . .
RUN pip install --upgrade pip
RUN pip install -e .

CMD ["fastapi", "dev", "--host", "0.0.0.0"]
# CMD ["fastapi", "dev", "--host", "0.0.0.0", "--port", "8000"]