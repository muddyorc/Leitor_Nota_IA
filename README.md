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
git clone https://github.com/seuusuario/NotaFiscalAI.git
cd NotaFiscalAI
```

### 🔹 2. Criar Ambiente Virtual

```bash
python -m venv venv
# Ativar ambiente virtual
# Windows
venv\Scripts\activate
# Linux / MacOS
source venv/bin/activate
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

## 📄 Considerações Finais

O NotaFiscalAI é modular, com código organizado em pastas (`services`, `config`, `uploads`, `templates`, `static`), seguindo boas práticas de desenvolvimento e fácil manutenção.

O projeto serve tanto como ferramenta prática quanto como exemplo de integração entre Flask, IA e manipulação de PDFs.

---

## 👥 Autor

📌 **Autor:** [Julio Cezar](https://github.com/seuusuario)

