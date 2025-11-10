import os
import json
from flask import Flask, jsonify, render_template, request
from config.settings import UPLOAD_FOLDER
from agents.AgenteExtracao.parser_service import extrair_texto_pdf
from agents.AgenteExtracao.ia_service import extrair_dados_com_llm
from agents.AgenteExtracao.utils import gerar_parcela_padrao
from agents.AgentePersistencia.processador import PersistenciaAgent


# ✅ novo import — agente de consulta RAG
from agents.consulta_rag.processador import ConsultaRagAgent

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

persistencia_agent = PersistenciaAgent()
consulta_agent = ConsultaRagAgent()  # ✅ nova instância do agente de consulta

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extrair', methods=['POST'])
def extrair():
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

    verificacao = persistencia_agent.verificar_entidades(dados_json)
    dados_json["_verificacao"] = verificacao

    return dados_json


@app.route('/lancar_conta', methods=['POST'])
def lancar_conta():
    try:
        dados_json = request.get_json(force=True)
    except Exception:
        return {"error": "JSON inválido"}, 400

    if not isinstance(dados_json, dict):
        return {"error": "Payload deve ser um objeto JSON"}, 400

    dados_para_persistir = {
        chave: valor for chave, valor in dados_json.items() if not chave.startswith("_")
    }

    if not dados_para_persistir:
        return {"error": "Dados ausentes para lançamento"}, 400

    try:
        resultado_persistencia = persistencia_agent.lancar_conta_pagar(dados_para_persistir)
    except Exception as exc:
        print(f"Erro ao persistir dados: {exc}")
        return {"error": "Falha ao persistir dados", "detalhes": str(exc)}, 500

    return jsonify({
        "mensagem": "Conta lançada com sucesso",
        "resultado": resultado_persistencia,
    })

@app.route('/consulta', methods=['GET'])
def consulta_page():
    """Renderiza a página da interface de consulta RAG."""
    return render_template('consulta.html')


@app.route('/consultar_rag', methods=['POST'])
def consultar_rag():
    """Processa uma pergunta e retorna a resposta do modelo via RAG."""
    try:
        payload = request.get_json(force=True)
    except Exception:
        return {"error": "JSON inválido"}, 400

    pergunta = payload.get('pergunta')
    modo = payload.get('modo') or 'simples'

    if not pergunta or not isinstance(pergunta, str):
        return {"error": "Pergunta inválida"}, 400

    try:
        if modo == 'semantico':
            resposta = consulta_agent.executar_consulta_semantica(pergunta)
        else:
            resposta = consulta_agent.executar_consulta_simples(pergunta)
    except Exception as exc:
        print(f"Erro ao processar RAG: {exc}")
        return {"error": "Falha na consulta RAG", "detalhes": str(exc)}, 500

    return jsonify({"resposta": resposta})


# Manter compatibilidade com rota antiga, se necessário
app.add_url_rule('/upload', view_func=extrair, methods=['POST'])

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug)
