import os
import json
from flask import Flask, render_template, request
from config.settings import UPLOAD_FOLDER
from agents.AgenteExtracao.parser_service import extrair_texto_pdf
from agents.AgenteExtracao.ia_service import extrair_dados_com_llm
from agents.AgenteExtracao.utils import gerar_parcela_padrao
from agents.AgentePersistencia.processador import PersistenciaAgent

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
persistencia_agent = PersistenciaAgent()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return {"error": "Nenhum arquivo enviado"}, 400

    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return {"error": "Arquivo inválido"}, 400

    texto_pdf = extrair_texto_pdf(file)
    if not texto_pdf:
        return {"error": "Não foi possível extrair texto do PDF"}, 500

    raw_json_str = extrair_dados_com_llm(texto_pdf)
    if not raw_json_str:
        return {"error": "Falha na comunicação com Gemini"}, 500

    clean_str = raw_json_str.replace("```json", "").replace("```", "").strip()
    try:
        dados_json = json.loads(clean_str)
    except json.JSONDecodeError:
        return {"error": "JSON inválido retornado pelo modelo", "resposta": clean_str}, 500

    dados_json = gerar_parcela_padrao(dados_json)

    try:
        resultado_persistencia = persistencia_agent.lancar_conta_pagar(dados_json)
    except Exception as exc:
        # Registrar no log padrão para facilitar depuração mantendo API informativa
        print(f"Erro ao persistir dados: {exc}")
        return {"error": "Falha ao persistir dados", "detalhes": str(exc)}, 500

    dados_json["_persistencia"] = resultado_persistencia

    return dados_json

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
