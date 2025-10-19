# 🧾 NotaFiscal AI – Extração Automática de Dados de Notas Fiscais

---

## 📌 Sobre o Projeto

O **NotaFiscalAI** é uma aplicação web desenvolvida com **Flask** que permite a extração automática de informações de arquivos PDF de notas fiscais.

O sistema utiliza inteligência artificial (**Google Gemini**) para processar o texto do PDF e retornar os dados em formato **JSON** e também em uma **visualização formatada**, facilitando o controle financeiro e a análise de despesas.

Desde a segunda etapa do projeto, o fluxo passou a ser dividido em duas fases:

- **Extração e verificação** (`/extrair`): o PDF é processado e o sistema consulta o banco para informar se fornecedor, faturado e classificações já existem, exibindo o status detalhado na interface.
- **Lançamento manual** (`/lancar_conta`): depois de revisar os dados, o usuário confirma o lançamento; o backend cria os registros que faltam e persiste o movimento e as parcelas.

O projeto é ideal para estudos, automação de processos financeiros e como base para sistemas que precisam interpretar documentos fiscais.

---

## 🚀 Começando

Este é um projeto **Flask** em Python, com persistência em **PostgreSQL** executado via Docker.

### 🔹 1. Clonar o Repositório

```bash
git clone https://github.com/muddyorc/Leitor_Nota_IA.git
cd Leitor_Nota_IA/extrair_dados_nota
```

### 🔹 2. Criar Ambiente Virtual (opcional; use os scripts prontos)

Você pode usar os scripts prontos abaixo para setup automático. Se preferir fazer manualmente, siga este passo.

```bash
python -m venv .venv
# Ativar ambiente virtual
# Windows
.venv\Scripts\activate
# Linux / MacOS
source .venv/bin/activate
```

### 🔹 3. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 🔹 4. Subir o PostgreSQL com Docker

É necessário ter **Docker** (e o plugin Compose ou `docker-compose`) instalado. Para iniciar o banco localmente utilizando o `docker-compose.yml` incluído no projeto:

```bash
docker compose up -d db
# ou
docker-compose up -d db
```

O serviço fica disponível em `localhost:5433`. O script de setup (`setup_and_run.sh` ou `.bat`) detecta automaticamente o Compose e oferece subir o banco caso não esteja rodando, mas é recomendável garantir que o Docker esteja ativo antes de executá-lo.

### 🔹 5. Configurar Variáveis de Ambiente

* Crie um arquivo `.env` na raiz do projeto (os scripts de setup já o criam automaticamente).
* Adicione sua chave da API do Gemini e, se desejar, personalize as credenciais do banco. Valores padrão:

```env
GOOGLE_API_KEY=your_google_api_key_here
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5433
DB_NAME=notas
```

### 🔹 6. Inicializar o Banco de Dados

Crie as tabelas definidas no ORM chamando o script de inicialização:

```bash
python -m database.init_db
```

> Dica: os scripts de setup (`setup_and_run.sh` / `.bat`) já executam esse comando automaticamente, aguardando o banco ficar pronto através do utilitário `database.wait_for_db`.

### 🔹 7. Criar Diretório de Uploads (se ainda não existir)

```bash
mkdir -p uploads
```

> Os scripts de setup criam automaticamente essa pasta ao final da execução.

### 🔹 8. Rodar o Servidor de Desenvolvimento

```bash
python app.py
```

Abra [http://localhost:5000](http://localhost:5000) no navegador para usar a aplicação.

---

## � Executando com Docker

Com o projeto containerizado, basta utilizar o Docker Compose para subir a aplicação e o banco:

```bash
docker compose up --build
```

No primeiro build a imagem da aplicação Flask será criada a partir do `Dockerfile` e o serviço PostgreSQL será iniciado automaticamente. As credenciais usadas vêm do `.env`, mas para o container o host e a porta são substituídos para apontar para o serviço `db` interno (`DB_HOST=db`, `DB_PORT=5432`).

- A aplicação web fica disponível em [http://localhost:5000](http://localhost:5000)
- Os dados do banco são persistidos no volume `postgres_data`
- Os arquivos enviados para `uploads/` ficam no volume `uploads_data`

Para desligar os serviços:

```bash
docker compose down
```

Se preferir remover os volumes (incluindo os dados do banco), acrescente `-v`:

```bash
docker compose down -v
```

---

## �🛠 Tecnologias Utilizadas

* **Python 3.10+**: linguagem principal
* **Flask**: microframework web para Python
* **Google Gemini**: inteligência artificial para extração de dados
* **SQLAlchemy**: ORM para modelagem e persistência dos dados
* **PostgreSQL 16**: banco de dados relacional (via Docker)
* **Docker Compose**: orquestração do serviço de banco de dados
* **python-dotenv**: carregamento de variáveis de ambiente
* **PyMuPDF (fitz)**: leitura e extração de texto de PDFs
* **Pillow + pytesseract**: OCR opcional para PDFs sem texto
* **HTML5, CSS3 e JavaScript**: interface web responsiva

---

## ⚙️ Scripts de Setup e Execução

Para facilitar o uso, o projeto inclui scripts de setup/execução. Eles criam a venv, instalam dependências, configuram o `.env` e tentam subir o PostgreSQL automaticamente (caso Docker/Compose esteja disponível):

- Linux/MacOS: `setup_and_run.sh`
- Windows: `setup_and_run.bat`

O que os scripts fazem:
- Checam Python 3 e criam venv `.venv`
- Instalam dependências (`requirements.txt`)
- Verificam o Tesseract (OCR opcional) e informam como instalar
- Preparam o arquivo `.env` pedindo a `GOOGLE_API_KEY` e preenchendo as variáveis do banco (`DB_*`)
- Se Docker Compose estiver disponível, sobem o serviço `db` do `docker-compose.yml`, aguardam o PostgreSQL inicializar com `python -m database.wait_for_db` e executam `python -m database.init_db` para garantir as tabelas
- Garantem a pasta `uploads/`
- Iniciam a aplicação com `python app.py`

Como usar:

Linux/MacOS:
```bash
chmod +x setup_and_run.sh
./setup_and_run.sh
```

Windows (duplo clique também funciona):
```bat
setup_and_run.bat
```

Opcionalmente, exporte a chave antes de rodar:

Linux/MacOS:
```bash
export GOOGLE_API_KEY="sua_chave"
./setup_and_run.sh
```

Windows:
```bat
set GOOGLE_API_KEY=sua_chave
setup_and_run.bat
```

---

## 🔍 Pré-requisitos de OCR (Tesseract)

Se o PDF não tiver texto embutido (apenas imagem), a aplicação usa OCR via `pytesseract` + binário `tesseract`.

O script `setup_and_run.sh` tenta instalar automaticamente o Tesseract nas distros mais comuns (apt/dnf/pacman) quando você concorda. Caso prefira instalar manualmente:

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

Se ainda aparecer a mensagem "tesseract is not installed or it's not in your PATH":
- Verifique se `tesseract` executa no terminal: `tesseract --version`.
- Reabra o terminal e rode novamente o script para atualizar o PATH da sessão.
- Em WSL/containers, confirme se o pacote foi instalado dentro do mesmo ambiente do Python.

---

## 🧪 Testes Automatizados

O projeto conta com uma suíte de testes (PyTest) cobrindo o agente de persistência, os endpoints `/extrair` e `/lancar_conta`, e o script de inicialização do banco. Para executá-la:

```bash
.venv/bin/python -m pytest
```

No Windows:

```bat
.venv\Scripts\python -m pytest
```

Os scripts de setup já criam e ativam a venv, então basta reutilizá-la.

---

## 📊 Inspecionando o Banco de Dados

Para navegar pelos dados de forma visual você pode usar ferramentas gráficas de PostgreSQL:

- **DBeaver Community** (Windows/Linux/macOS): após instalar, crie uma conexão com `localhost`, porta `5433`, banco `notas`, usuário e senha `postgres`.
- **pgAdmin 4 via Docker**: execute
	```bash
	docker run -d --name pgadmin -p 5050:80 \
		-e PGADMIN_DEFAULT_EMAIL=admin@example.com \
		-e PGADMIN_DEFAULT_PASSWORD=admin \
		--network extrair_dados_nota_default \
		dpage/pgadmin4
	```
	Em seguida acesse http://localhost:5050 e cadastre um servidor apontando para o host `leitor_nota_db` (ou `localhost:5433` se exposto localmente) com usuário/senha `postgres`.

---

## 🔄 Fluxo na Interface Web

1. Selecione um PDF de nota fiscal e clique em **EXTRAIR DADOS**.
2. Revise a visualização formatada e a aba JSON.
3. No cartão **Verificação no Sistema**, confira os status:
	 - Fornecedor e faturado exibem nome, documento e se já existem (com ID quando aplicável).
	 - Cada despesa classificada informa se já está cadastrada.
4. Caso esteja tudo correto, clique em **LANÇAR NO SISTEMA** para persistir os dados.
5. Uma mensagem confirma o sucesso ou aponta o erro encontrado.

---

## 📄 Considerações Finais

O NotaFiscalAI é modular, com código organizado em pastas (`agents`, `database`, `config`, `uploads`, `templates`, `static`), seguindo boas práticas de desenvolvimento e fácil manutenção.

O projeto serve tanto como ferramenta prática quanto como exemplo de integração entre Flask, IA e manipulação de PDFs.

---

## 👥 Autor

📌 **Autores:** 
* [Julio Cezar](https://github.com/muddyorc)
* [Rian Guedes](https://github.com/riangrodrigues)

