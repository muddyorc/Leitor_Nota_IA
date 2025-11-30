# Manual de Acesso

Este guia resume os links e os passos mínimos para validar a entrega em produção.

## 📁 Repositório
- GitHub (público): https://github.com/muddyorc/Leitor_Nota_IA

## ☁️ Aplicação hospedada
- Render (backend Flask + UI): [Leitor Nota IA](https://leitor-nota-ia.onrender.com/)
- Status esperado: após o deploy, acessar a URL deve exibir a dashboard "Leitor Nota IA".

> ⚠️ Caso utilize outro provedor (PythonAnywhere, etc.), substitua pelo link correspondente.

## 🔐 Credenciais / Chaves
- O sistema não exige login.
- A chave do Gemini **não** deve ser publicada; forneça-a via variável de ambiente `GOOGLE_API_KEY` no Render **ou** cole manualmente na seção “Configurar chave do Gemini” presente nas telas de Extração/RAG.

## ✅ Passo a passo de validação
1. Acesse o link do Render informado acima.
2. Na primeira carga, informe a chave do Gemini caso a tela indique que não há chave ativa.
3. Na aba **Extração**:
   - Clique em “Selecione o arquivo PDF”, escolha uma nota fiscal de teste e envie.
   - Aguarde a extração; revise os dados apresentados e utilize “LANÇAR NO SISTEMA” para gravar (opcional).
4. Na aba **Consulta RAG**:
   - Informe uma pergunta (ex.: “Quais foram os maiores gastos com manutenção?”) e escolha o modo desejado.
   - Verifique se a resposta retorna dados consistentes com o banco.
5. (Opcional) Navegue pelas abas **Contas/Pessoas/Classificações** para conferir o CRUD e os dados seedados.

## 🧪 Testes locais (caso necessário)
1. Clone o repositório e copie `.env.example` para `.env`.
2. Preencha `GOOGLE_API_KEY` e, se quiser reproduzir o cenário do Render, defina `DATABASE_URL` para o Postgres hospedado.
3. Execute `python -m database.init_db` e `python scripts/seed_database.py`.
4. Rode `python app.py` ou `docker compose up --build`.

## 📝 Observações
- Sempre confirme que o link do GitHub e o link público da aplicação estão acessíveis antes de entregar.
- Caso precise resetar o banco do Render, execute `python scripts/seed_database.py` localmente exportando `DATABASE_URL` com a *External Database URL* temporariamente.
