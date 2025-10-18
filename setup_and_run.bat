@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Script de setup e execução da aplicação Flask (Windows)
REM - Cria venv .venv
REM - Instala dependências
REM - Checa Tesseract (opcional para OCR)
REM - Prepara .env com GOOGLE_API_KEY
REM - Cria pasta uploads\
REM - Sobe a aplicação

cd /d "%~dp0"

echo ==^> Checando Python 3...
where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo Erro: Python 3 nao encontrado. Instale o Python 3 e tente novamente.
    exit /b 1
  ) else (
    set PY=py -3
  )
) else (
  set PY=python
)

echo ==^> Criando/ativando ambiente virtual (.venv)...
if not exist .venv (
  %PY% -m venv .venv
)

REM Ativar venv para a sessao atual
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo Erro ao ativar a venv. Verifique a instalacao do Python/venv.
  exit /b 1
)

echo ==^> Atualizando pip/setuptools/wheel...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :pip_fail

echo ==^> Instalando dependencias Python...
if exist requirements.txt (
  pip install -r requirements.txt
) else (
  pip install Flask python-dotenv google-generativeai PyMuPDF python-dateutil Pillow pytesseract
)
if errorlevel 1 goto :pip_fail

echo ==^> Verificando Tesseract OCR (opcional)...
where tesseract >nul 2>&1
if errorlevel 1 (
  echo AVISO: 'tesseract' nao encontrado. O OCR ficara desabilitado.
  echo Para instalar no Windows, baixe o instalador em:
  echo   https://github.com/UB-Mannheim/tesseract/wiki ^(versao recomendada para Windows^)
)

echo ==^> Preparando arquivo .env...
if not exist .env (
  type nul > .env
)

REM Se nao houver GOOGLE_API_KEY no .env e nem em ambiente, solicitar ao usuario
findstr /b /c:"GOOGLE_API_KEY=" .env >nul 2>&1
if errorlevel 1 (
  if "%GOOGLE_API_KEY%"=="" (
    set /p USER_KEY=Informe sua GOOGLE_API_KEY ^(Gemini^). Deixe em branco para pular: 
    if not "%USER_KEY%"=="" (
      >> .env echo GOOGLE_API_KEY=%USER_KEY%
      echo .env atualizado com GOOGLE_API_KEY.
    ) else (
      echo Sem GOOGLE_API_KEY: as chamadas a IA ^(Gemini^) nao funcionarao.
    )
  )
)

call :ensure_env_var DB_USER postgres
call :ensure_env_var DB_PASSWORD postgres
call :ensure_env_var DB_HOST localhost
call :ensure_env_var DB_PORT 5433
call :ensure_env_var DB_NAME notas

echo ==^> Garantindo diretorio uploads\
if not exist uploads (
  mkdir uploads
)

echo ==^> Iniciando a aplicacao Flask...
python app.py
goto :eof

:ensure_env_var
findstr /b /c:"%1=" .env >nul 2>&1
if errorlevel 1 (
  >> .env echo %1=%2
  echo .env atualizado com %1=%2.
)
goto :eof

:pip_fail
echo Falha ao instalar dependencias com pip. Verifique sua conexao e tente novamente.
exit /b 1

endlocal
