#!/bin/sh
set -e

echo "🚀 Iniciando Container no Render..."

# --- 1. Inicialização do Banco de Dados ---
# REMOVIDO: python -m database.wait_for_db (Causava timeout no deploy)
# Tenta criar tabelas, mas não falha se o banco já estiver pronto (|| true)
echo "🛠️ Tentando inicializar banco (se possível)..."
python -m database.init_db || echo "⚠️ Aviso: Inicialização do DB falhou ou já estava pronto. Continuando..."

# Cria pasta de uploads para garantir que existe
mkdir -p uploads

# --- 2. Indexação RAG (Opcional) ---
# Executa apenas se não houver indice e não for pulado via env var
if [ "${SKIP_RAG_INDEX:-0}" != "1" ]; then
    if [ ! -f "${CHROMA_DIR:-./_chromadb}/chroma.sqlite3" ]; then
        echo "[entrypoint] Executando indexação RAG..."
        # '|| true' impede que falta de RAM mate o deploy
        python scripts/indexar_dados.py || echo "⚠️ Aviso: Indexação RAG falhou (provavelmente RAM). O app vai subir sem dados novos."
    else
        echo "[entrypoint] Índice Chroma já existente."
    fi
fi

# --- 3. Configuração do Servidor Web ---
APP_MODULE=${APP_MODULE:-main:app} # Confirme se é main:app ou app:app
GUNICORN_HOST=0.0.0.0
GUNICORN_PORT=${PORT:-5000}        # Render injeta a porta automaticamente
GUNICORN_WORKERS=2                 # Reduzido para 2 para economizar RAM no Free Tier
GUNICORN_TIMEOUT=120               # Timeout maior para evitar erros 502 na inicialização

echo "✅ Iniciando Gunicorn na porta $GUNICORN_PORT..."

# Executa o servidor. Se o banco estiver fora, o erro aparecerá no log do Gunicorn.
exec gunicorn "$APP_MODULE" \
    --bind "${GUNICORN_HOST}:${GUNICORN_PORT}" \
    --workers "${GUNICORN_WORKERS}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --access-logfile '-' \
    --error-logfile '-'