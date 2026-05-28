FROM python:3.12-slim

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ffmpeg tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
