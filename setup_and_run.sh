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
  if [ -t 0 ]; then
    echo -n "Deseja que eu tente instalar automaticamente? [s/N]: "
    read -r INSTALL_TESS
  else
    INSTALL_TESS="n"
  fi

  if [[ "${INSTALL_TESS,,}" == "s" || "${INSTALL_TESS,,}" == "sim" ]]; then
    if command -v apt >/dev/null 2>&1; then
      echo "==> Instalando via apt..."
      # Tenta atualizar, mas não falha se algum PPA estiver quebrado
      sudo apt update || true
      # Tenta instalar mesmo se o update falhar
      sudo apt install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng poppler-utils || true
    elif command -v dnf >/dev/null 2>&1; then
      echo "==> Instalando via dnf..."
      sudo dnf install -y tesseract tesseract-langpack-por tesseract-langpack-eng poppler-utils || true
    elif command -v pacman >/dev/null 2>&1; then
      echo "==> Instalando via pacman..."
      sudo pacman -S --noconfirm tesseract tesseract-data-por tesseract-data-eng poppler || true
    else
      echo "Não foi possível detectar o gerenciador de pacotes. Instale o 'tesseract-ocr' manualmente."
    fi

    if command -v tesseract >/dev/null 2>&1; then
      echo "Instalação do tesseract concluída com sucesso."
    else
      echo "Falha ao instalar tesseract automaticamente. Consulte o README para instruções manuais."
    fi
  else
    echo "Você pode instalar manualmente conforme sua distribuição:"
    if command -v apt >/dev/null 2>&1; then
      echo "  sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng poppler-utils"
    elif command -v dnf >/dev/null 2>&1; then
      echo "  sudo dnf install -y tesseract tesseract-langpack-por tesseract-langpack-eng poppler-utils"
    elif command -v pacman >/dev/null 2>&1; then
      echo "  sudo pacman -S tesseract tesseract-data-por tesseract-data-eng poppler"
    else
      echo "  Consulte a documentação da sua distribuição para instalar 'tesseract-ocr'."
    fi
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

# Garantir variáveis padrão do banco de dados caso não existam
ensure_env_var() {
  local key="$1"
  local default_value="$2"
  if ! grep -q "^${key}=" .env >/dev/null 2>&1; then
    printf '%s=%s\n' "$key" "$default_value" >> .env
    echo ".env atualizado com ${key}=${default_value}."
  fi
}

ensure_env_var "DB_USER" "postgres"
ensure_env_var "DB_PASSWORD" "postgres"
ensure_env_var "DB_HOST" "localhost"
ensure_env_var "DB_PORT" "5433"
ensure_env_var "DB_NAME" "notas"

detect_compose_cmd() {
  if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      COMPOSE_CMD=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
      COMPOSE_CMD=(docker-compose)
    else
      COMPOSE_CMD=()
    fi
  else
    COMPOSE_CMD=()
  fi
}

wait_for_database() {
  echo "==> Aguardando PostgreSQL inicializar..."
  if python -m database.wait_for_db; then
    return 0
  fi
  echo "AVISO: PostgreSQL não respondeu a tempo."
  return 1
}

ensure_database_running() {
  detect_compose_cmd
  if [ ${#COMPOSE_CMD[@]} -eq 0 ]; then
    echo "AVISO: Docker Compose não encontrado. Suba o PostgreSQL manualmente antes de executar a aplicação."
    return
  fi

  if [ ! -f docker-compose.yml ]; then
    echo "AVISO: docker-compose.yml não encontrado. Configure o banco manualmente se necessário."
    return
  fi

  echo "==> Verificando serviço PostgreSQL via Docker Compose..."
  local running
  if [ "${COMPOSE_CMD[0]}" = "docker" ]; then
    running="$(${COMPOSE_CMD[@]} ps --status running --services 2>/dev/null || true)"
  else
    running="$(${COMPOSE_CMD[@]} ps --services --filter "status=running" 2>/dev/null || true)"
  fi

  if ! grep -q '^db$' <<<"$running"; then
    if [ -t 0 ]; then
      read -r -p "Serviço 'db' não está em execução. Deseja iniciar com Docker Compose? [S/n]: " answer
    else
      answer="s"
    fi
    if [[ "${answer,,}" != "n" ]]; then
      if ! ${COMPOSE_CMD[@]} up -d db; then
        echo "Erro ao iniciar o banco via Docker Compose. Verifique permissões (grupo docker) e tente novamente."
        return
      fi
    else
      echo "Prosseguindo sem subir o PostgreSQL automaticamente."
      return
    fi
  else
    echo "Banco já está em execução."
  fi

  if wait_for_database; then
    echo "==> Aplicando migrações/tabelas (database.init_db)..."
    if ! python -m database.init_db; then
      echo "AVISO: não foi possível criar as tabelas automaticamente."
    fi
  else
    echo "AVISO: prosseguindo sem aplicar database.init_db porque o banco não respondeu a tempo."
  fi
}

ensure_database_running

echo "==> Garantindo diretório de uploads/"
mkdir -p uploads

echo "==> Iniciando a aplicação Flask..."
exec python app.py
