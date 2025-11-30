# 🧾 NotaFiscal AI – Extração Automática de Dados de Notas Fiscais

---

## 📌 Sobre o Projeto

O **NotaFiscalAI** é uma aplicação web desenvolvida com **Flask** que automatiza a extração de informações de PDFs de notas fiscais.

O sistema utiliza inteligência artificial (**Google Gemini**) para interpretar o conteúdo dos arquivos e devolver os dados tanto em formato **JSON** quanto em uma **visualização amigável**, simplificando a conferência e o lançamento financeiro. A partir da Etapa 3, a aplicação passou a oferecer também uma interface de **consulta RAG** (Retrieval-Augmented Generation), permitindo perguntas em linguagem natural sobre as contas já persistidas.

O fluxo completo é dividido em três etapas principais:

- **Extração e verificação** (`/extrair`): processa o PDF e consulta o banco para informar se fornecedor, faturado e classificações já existem.
- **Lançamento manual** (`/lancar_conta`): após revisão, cria os registros faltantes e grava o movimento e as parcelas.
- **Consulta RAG** (`/consulta`): página dedicada para perguntas em linguagem natural, com modos **Simples (SQL)** e **Semântico (ChromaDB + Sentence-Transformers)**.

O projeto serve como base para automação de contas a pagar, estudos de integração entre IA e documentos fiscais e demonstração de consultas RAG sobre dados estruturados.

---

## 🚀 Começando

Este é um projeto **Flask** com persistência em **PostgreSQL** (via Docker) e suporte opcional a OCR (Tesseract).

### 🔹 1. Clonar o Repositório

```bash
git clone https://github.com/muddyorc/Leitor_Nota_IA.git
cd Leitor_Nota_IA/extrair_dados_nota
```

### 🔹 2. Criar Ambiente Virtual (opcional: os scripts prontos já fazem isso)

```bash
python -m venv .venv
# Ativar ambiente virtual
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

### 🔹 3. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 🔹 4. Subir o PostgreSQL com Docker

```bash
docker compose up -d db
# ou, se estiver usando docker-compose clássico
docker-compose up -d db
```

O serviço ficará disponível em `localhost:5433`. Os scripts `setup_and_run.sh` / `.bat` detectam o Docker e perguntam se você deseja subir o banco automaticamente.

### 🔹 5. Configurar Variáveis de Ambiente

Crie um arquivo `.env` na raiz (os scripts de setup criam automaticamente) e informe sua chave do Gemini:

```env
GOOGLE_API_KEY=your_google_api_key_here
# Opcional: string completa do Postgres (Render fornece Internal/External URLs)
# DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/notas
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5433
DB_NAME=notas
# Opcional: caminho onde o ChromaDB salva o índice vetorial quando rodar localmente
# CHROMA_DIR=./_chromadb
```

> Se `DATABASE_URL` estiver definido, ele sobrescreve `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` e `DB_NAME`. Use-o para apontar diretamente para o Postgres hospedado no Render.
>
> ⚠️ Quando a variável `GOOGLE_API_KEY` não estiver presente (ex.: ambientes compartilhados), utilize a seção **“Configurar chave do Gemini”** disponível nas páginas de Extração e Consulta RAG. A chave é armazenada apenas na sessão do navegador e não é enviada ao GitHub.

### 🔹 6. Inicializar o Banco de Dados

```bash
python -m database.init_db
```

> Os scripts de setup aguardam o banco ficar pronto (`python -m database.wait_for_db`) e chamam esse comando automaticamente.

### 🔹 7. Criar Diretório de Uploads

```bash
mkdir -p uploads
```

### 🔹 8. Popular o banco com dados de teste (Seed)

O enunciado demanda um ambiente navegável com pelo menos 200 registros. Rode o script abaixo
uma única vez (após `python -m database.init_db`) para gerar ~50 pessoas, ~10 classificações e 200
movimentos distribuídos em datas aleatórias:

```bash
python scripts/seed_database.py
```

Se precisar repetir o processo, utilize `--force` para ignorar a checagem de dados existentes e
`--seed 42` (por exemplo) para resultados reproduzíveis. Há também parâmetros opcionais como
`--movimentos 300` para ajustar volumes específicos.

### 🔹 9. (Opcional) Indexar dados para o modo semântico

Depois de ter alguns movimentos cadastrados (ou após rodar a extração), execute:

```bash
python scripts/indexar_dados.py
```

Isso gera/atualiza o índice vetorial do ChromaDB usado pelo modo semântico.

### 🔹 10. Rodar o Servidor de Desenvolvimento

```bash
python app.py
```

Abra [http://localhost:5000](http://localhost:5000) no navegador.

---

## 📦 Executando com Docker

```bash
docker compose up --build
```

O `Dockerfile` instala as dependências, o `docker-entrypoint.sh` aguarda o banco, roda `python -m database.init_db` e executa `scripts/indexar_dados.py` caso ainda não exista um índice vetorial (pode ser pulado definindo `SKIP_RAG_INDEX=1`). Em seguida o servidor **gunicorn** é iniciado escutando em `0.0.0.0:${PORT:-5000}` (a variável `PORT` pode ser definida pelo provedor de nuvem ou manualmente).

- Antes de levantar os containers, copie `.env.example` para `.env` e configure `GOOGLE_API_KEY`.
- A aplicação web fica acessível em [http://localhost:5000](http://localhost:5000).
- Os dados são persistidos em volumes:
  - `postgres_data`: dados do PostgreSQL.
  - `uploads_data`: arquivos enviados.
  - `chroma_data`: índice vetorial do ChromaDB (`/app/_chromadb`).

Para desligar:

```bash
docker compose down
```

Para remover volumes:

```bash
docker compose down -v
```

---

## ☁️ Deploy em Produção (Render / PythonAnywhere)

As etapas abaixo cumprem o **Bloco de Tarefas 3** e permitem subir o backend em um ambiente distribuído.

### 1. Variáveis obrigatórias

Configure os seguintes valores no painel do provedor (nunca commite um `.env` com chaves reais):

- `GOOGLE_API_KEY`
- `DATABASE_URL` (string completa do PostgreSQL provido pelo Render ou outro serviço)
- `FLASK_SECRET_KEY`
- `CHROMA_DIR` (opcional – ex.: `/tmp/chroma` quando rodar em container efêmero)
- `SKIP_RAG_INDEX=1` (opcional, quando preferir indexar manualmente)

### 2. Banco de Dados no Render

1. Crie/acesse uma conta em [render.com](https://render.com/).
2. Vá em **New ➜ PostgreSQL** e escolha o plano gratuito ou o que fizer sentido.
3. Após a criação, copie:
  - **Internal Database URL** → use dentro do próprio Render (variável `DATABASE_URL`).
  - **External Database URL** → use localmente para migrações/seeds (por exemplo, exporte a URL e rode `DATABASE_URL=... python scripts/seed_database.py`).
4. Atualize seu `.env` local para apontar para essa URL quando precisar testar contra o banco hospedado.

### 3. Backend no Render (Web Service Docker)

1. Clique em **New ➜ Web Service** e conecte o repositório `muddyorc/Leitor_Nota_IA` (branch `feature/etapa4-crud-ui` ou `main`).
2. Selecione **Docker** como ambiente de build. O Render detectará o `Dockerfile` e executará `docker build` automaticamente.
3. Não há comando de start manual: o `docker-entrypoint.sh` já executa `python -m database.wait_for_db`, `python -m database.init_db`, indexa (se necessário) e inicia o `gunicorn`.
4. Defina as variáveis de ambiente citadas acima no painel **Environment**.
5. Garanta que o serviço do banco (Internal Database) esteja listado em **Environment ➜ Private Services** para autenticar via rede interna.
6. Caso o Render forneça um `PORT`, ele será honrado automaticamente. Em motores que não definem `PORT`, configure um valor (ex.: `5000`).

### 4. Backend no PythonAnywhere (alternativa sem Docker)

1. Faça upload do código ou conecte o repositório via Git.
2. Crie um **Virtualenv Python 3.12** e rode `pip install -r requirements.txt`.
3. Defina as variáveis de ambiente em **Web ➜ WSGI configuration** (use `os.environ[...] = ...`).
4. Ajuste o arquivo WSGI para expor a aplicação: `from app import app as application`.
5. Antes do primeiro request, rode `python -m database.init_db` no console apontando para o mesmo `DATABASE_URL` do Render (ou um Postgres hospedado no próprio PythonAnywhere se preferir).

### 5. Frontend na Vercel (opcional)

Este projeto usa Flask + Jinja para servir o frontend. Só utilize a Vercel caso você extraia as telas para um SPA (React/Vue). Nesse cenário, exponha apenas a API Flask (Render/PythonAnywhere) e configure as origens permitidas.

---

## 📗 Manual de acesso

Consulte `MANUAL_ACESSO.md` para encontrar (e atualizar) os links públicos, passos de validação e orientações sobre credenciais/chaves antes da entrega final.

---

## ⚙️ Scripts de Setup e Execução

- Linux/macOS: `setup_and_run.sh`
- Windows: `setup_and_run.bat`

Eles realizam:

- Criação/ativação da venv `.venv`.
- Instalação das dependências (`requirements.txt`).
- Configuração do `.env` (solicitando a chave do Gemini e preenchendo credenciais padrão do banco).
- Verificações de Tesseract e instruções de instalação (opcional).
- Subida opcional do serviço PostgreSQL via Docker Compose e inicialização de tabelas.
- Criação da pasta `uploads/`.
- Execução da aplicação (`python app.py`).
- Orientação para rodar `python scripts/indexar_dados.py` quando desejar habilitar a consulta semântica fora do Docker.

Como usar no Linux/macOS:

```bash
chmod +x setup_and_run.sh
./setup_and_run.sh
```

No Windows:

```bat
setup_and_run.bat
```

---

## 🔎 Consultas com RAG

1. Acesse `/consulta` ou clique em **Consulta RAG** na UI.
2. Escolha o modo **Simples (SQL)** ou **Semântico (ChromaDB)**.
3. Escreva a pergunta em linguagem natural (ex.: "Quais foram as últimas contas lançadas para manutenção?").
4. O frontend envia um POST para `/consultar_rag`. O backend recupera o contexto correspondente, injeta no prompt do Gemini e retorna a resposta.
5. Para manter o modo semântico atualizado fora do Docker, execute `python scripts/indexar_dados.py` sempre que novos movimentos relevantes forem inseridos.

> 💡 O RAG **Simples** agora possui um classificador leve de intenções. Perguntas sobre contas a pagar recentes, fornecedores com muitos lançamentos, parcelas em aberto, classificações mais onerosas e notas do tipo RECEBER são respondidas diretamente com SQL parametrizado antes mesmo de chamar o LLM. Para outros cenários, o comportamento segue igual: o contexto em texto é montado e o Gemini responde com base nos registros disponíveis.

---

## 🔍 Pré-requisitos de OCR (Tesseract)

Quando o PDF não contém texto embutido, a aplicação usa OCR via `pytesseract` + binário `tesseract`.

Instalação manual:

- Debian/Ubuntu:
  ```bash
  sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng poppler-utils
  ```
- Fedora:
  ```bash
  sudo dnf install -y tesseract tesseract-langpack-por tesseract-langpack-eng poppler-utils
  ```
- Arch/Manjaro:
  ```bash
  sudo pacman -S tesseract tesseract-data-por tesseract-data-eng poppler
  ```

Os scripts de setup detectam e orientam caso o Tesseract não esteja instalado.

---

## 🧪 Testes Automatizados

```bash
.venv/bin/python -m pytest
```

No Windows:

```bat
.venv\Scripts\python -m pytest
```

---

## 📊 Inspecionando o Banco de Dados

- **DBeaver Community**: configure conexão `localhost:5433`, banco `notas`, usuário/senha `postgres`.
- **pgAdmin 4 (Docker)**:
  ```bash
  docker run -d --name pgadmin -p 5050:80 \
    -e PGADMIN_DEFAULT_EMAIL=admin@example.com \
    -e PGADMIN_DEFAULT_PASSWORD=admin \
    --network extrair_dados_nota_default \
    dpage/pgadmin4
  ```
  Depois acesse http://localhost:5050 e adicione servidor apontando para `leitor_nota_db`.

---

## 🔄 Fluxo na Interface Web

1. Faça upload do PDF e clique em **EXTRAIR DADOS**.
2. Revise a visualização formatada e o JSON retornado.
3. Confira o cartão **Verificação no Sistema** para verificação de fornecedor, faturado e categorias.
4. Clique em **LANÇAR NO SISTEMA** para persistir os dados.
5. Use a aba **Consulta RAG** para responder perguntas sobre lançamentos já gravados.

---

## 🛠 Tecnologias Utilizadas

- **Python 3.12+**
- **Flask**
- **Google Gemini**
- **SQLAlchemy**
- **PostgreSQL 16**
- **Docker & Docker Compose**
- **python-dotenv**
- **PyMuPDF (fitz)**
- **Pillow + pytesseract**
- **HTML5, CSS3, JavaScript**
- **ChromaDB + Sentence-Transformers** (RAG semântico)

---

## 📄 Considerações Finais

O NotaFiscalAI é modular, organizado em pastas (`agents`, `database`, `config`, `templates`, `static`, etc.) e combina processamento de documentos, inteligência artificial e consultas RAG. Ele pode ser usado tanto como ferramenta prática quanto como base para estudos e evoluções futuras.

---

## 👥 Autores

- [Julio Cezar](https://github.com/muddyorc)
- [Rian Guedes](https://github.com/riangrodrigues)

