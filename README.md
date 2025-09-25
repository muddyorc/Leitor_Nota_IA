# 🧾 NotaFiscal AI – Extração Automática de Dados de Notas Fiscais

---

## 📌 Sobre o Projeto

O **NotaFiscalAI** é uma aplicação web desenvolvida com **Flask** que permite a extração automática de informações de arquivos PDF de notas fiscais.

O sistema utiliza inteligência artificial (**Google Gemini**) para processar o texto do PDF e retornar os dados em formato **JSON** e também em uma **visualização formatada**, facilitando o controle financeiro e a análise de despesas.

O projeto é ideal para estudos, automação de processos financeiros e como base para sistemas que precisam interpretar documentos fiscais.

---

## 🚀 Começando

Este é um projeto **Flask** em Python.

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

### 🔹 4. Configurar Variáveis de Ambiente

* Crie um arquivo `.env` na raiz do projeto.
* Adicione sua chave da API do Gemini:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

### 🔹 5. Criar Diretório de Uploads

```bash
mkdir uploads
```

### 🔹 6. Rodar o Servidor de Desenvolvimento

```bash
python app.py
```

Abra [http://localhost:5000](http://localhost:5000) no navegador para usar a aplicação.

---

## 🛠 Tecnologias Utilizadas

* **Python 3.10+**: linguagem principal
* **Flask**: microframework web para Python
* **Google Gemini**: inteligência artificial para extração de dados
* **PyMuPDF (fitz)**: leitura e extração de texto de PDFs
* **Pillow + pytesseract**: OCR opcional para PDFs sem texto
* **HTML5, CSS3 e JavaScript**: interface web responsiva

---

## ⚙️ Scripts de Setup e Execução

Para facilitar o uso, o projeto inclui scripts de setup/execução:

- Linux/MacOS: `setup_and_run.sh`
- Windows: `setup_and_run.bat`

O que os scripts fazem:
- Checam Python 3 e criam venv `.venv`
- Instalam dependências (`requirements.txt`)
- Verificam o Tesseract (OCR opcional) e informam como instalar
- Preparam o arquivo `.env` pedindo a `GOOGLE_API_KEY` (ou usam a variável já exportada)
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

## � Pré-requisitos de OCR (Tesseract)

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

## �📄 Considerações Finais

O NotaFiscalAI é modular, com código organizado em pastas (`services`, `config`, `uploads`, `templates`, `static`), seguindo boas práticas de desenvolvimento e fácil manutenção.

O projeto serve tanto como ferramenta prática quanto como exemplo de integração entre Flask, IA e manipulação de PDFs.

---

## 👥 Autor

📌 **Autor:** [Julio Cezar](https://github.com/muddyorc)

