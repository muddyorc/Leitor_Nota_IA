#!/usr/bin/env sh
set -e

python -m database.wait_for_db
python -m database.init_db || true
mkdir -p uploads

# Indexa dados para o ChromaDB somente se ainda não houver vetor armazenado
if [ "${SKIP_RAG_INDEX:-0}" != "1" ]; then
	if [ ! -f "${CHROMA_DIR:-./_chromadb}/chroma.sqlite3" ]; then
		echo "[entrypoint] Executando indexação RAG no ChromaDB..."
		python scripts/indexar_dados.py || echo "[entrypoint] Aviso: indexação RAG falhou; continuei mesmo assim."
	else
		echo "[entrypoint] Índice Chroma já existente, pulando indexação."
	fi
fi

APP_MODULE=${APP_MODULE:-app:app}
GUNICORN_HOST=${GUNICORN_HOST:-0.0.0.0}
GUNICORN_PORT=${PORT:-5000}
GUNICORN_WORKERS=${GUNICORN_WORKERS:-3}
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120}

exec gunicorn "$APP_MODULE" \
	--bind "${GUNICORN_HOST}:${GUNICORN_PORT}" \
	--workers "${GUNICORN_WORKERS}" \
	--timeout "${GUNICORN_TIMEOUT}" \
	--access-logfile '-' --error-logfile '-'
