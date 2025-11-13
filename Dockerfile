# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROMA_DIR=/app/_chromadb

WORKDIR /app

# Install system dependencies required by PyMuPDF and psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc git poppler-utils tesseract-ocr tesseract-ocr-por tesseract-ocr-eng libgl1 libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p ${CHROMA_DIR} /app/uploads && \
    chmod +x docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./docker-entrypoint.sh"]
