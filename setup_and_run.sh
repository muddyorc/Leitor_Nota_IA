#!/usr/bin/env bash
set -Eeuo pipefail

# Script de setup e execução da aplicação Flask (Linux)
# - Cria venv .venv
# - Instala dependências
# - Checa tesseract (opcional para OCR)
# - Prepara .env com GOOGLE_API_KEY
# - Cria pasta uploads/
# - Sobe a aplicação

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "==> Checando Python 3..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Erro: Python 3 não encontrado. Instale o Python 3 e tente novamente."
  exit 1
fi

PYTHON=python3

echo "==> Criando/ativando ambiente virtual (.venv)..."
if [ ! -d ".venv" ]; then
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Atualizando pip/setuptools/wheel..."
python -m pip install --upgrade pip setuptools wheel

echo "==> Instalando dependências Python..."
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  pip install Flask python-dotenv google-generativeai PyMuPDF python-dateutil Pillow pytesseract
fi

echo "==> Verificando tesseract-ocr (para OCR opcional)..."
if ! command -v tesseract >/dev/null 2>&1; then
  echo "AVISO: 'tesseract' não encontrado. O OCR ficará desabilitado."
  echo "Para instalar o tesseract-ocr, use um dos comandos abaixo conforme sua distribuição:"
  if command -v apt >/dev/null 2>&1; then
    echo "  sudo apt update && sudo apt install -y tesseract-ocr"
  elif command -v dnf >/dev/null 2>&1; then
    echo "  sudo dnf install -y tesseract"
  elif command -v pacman >/dev/null 2>&1; then
    echo "  sudo pacman -S tesseract"
  else
    echo "  Consulte a documentação da sua distribuição para instalar 'tesseract-ocr'."
  fi
fi

echo "==> Preparando arquivo .env..."
if [ ! -f .env ]; then
  touch .env
fi

# Se não houver GOOGLE_API_KEY no ambiente e nem no .env, solicitar ao usuário
if ! grep -q '^GOOGLE_API_KEY=' .env >/dev/null 2>&1; then
  if [ -z "${GOOGLE_API_KEY:-}" ]; then
    echo
    echo "Informe sua GOOGLE_API_KEY (Gemini). Deixe em branco para pular:"
    read -r -s USER_KEY
    echo
    if [ -n "$USER_KEY" ]; then
      printf 'GOOGLE_API_KEY=%s\n' "$USER_KEY" >> .env
      echo ".env atualizado com GOOGLE_API_KEY."
    else
      echo "Sem GOOGLE_API_KEY: as chamadas à IA (Gemini) não funcionarão."
    fi
  fi
fi

echo "==> Garantindo diretório de uploads/"
mkdir -p uploads

echo "==> Iniciando a aplicação Flask..."
exec python app.py
