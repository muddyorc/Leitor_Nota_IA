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

exec python app.py
