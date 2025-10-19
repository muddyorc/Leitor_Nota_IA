# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies required by PyMuPDF and psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc poppler-utils tesseract-ocr tesseract-ocr-por tesseract-ocr-eng && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
