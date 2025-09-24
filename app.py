import os
import json
from flask import Flask, render_template, request
from config.settings import UPLOAD_FOLDER
from services.parser_service import extrair_texto_pdf
from services.ia_service import extrair_dados_com_llm
from services.utils import gerar_parcela_padrao, classificar_nota_fiscal

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
    dados_json["classificacaoDespesa"] = classificar_nota_fiscal(dados_json)

    return dados_json  

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
