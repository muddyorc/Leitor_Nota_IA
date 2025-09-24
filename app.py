import os
import fitz  
import json
from flask import Flask, render_template, request
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta

# OCR opcional
try:
    import pytesseract
    from PIL import Image
    OCR_DISPONIVEL = True
except ImportError:
    OCR_DISPONIVEL = False

# Carrega variáveis de ambiente
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Erro: GOOGLE_API_KEY não encontrada no .env")
    exit()

genai.configure(api_key=GOOGLE_API_KEY)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# ---------------- Motor de Regras ----------------
REGRAS_DE_CLASSIFICACAO = {
    "INSUMOS AGRÍCOLAS": [
    "semente", "sementes", "fertilizante", "fertilizantes",
    "defensivo", "defensivos", "agrotóxico", "herbicida",
    "inseticida", "fungicida", "adubo", "corretivo", "calcário"
],

"MANUTENÇÃO E OPERAÇÃO": [
    "combustível", "diesel", "gasolina", "etanol",
    "óleo", "graxa", "lubrificante", "peça", "peças",
    "parafuso", "rolamento", "retentor", "embreagem",
    "manutenção", "reparo", "conserto", "pneu", "filtro",
    "correia", "ferramenta", "bateria"
],

"RECURSOS HUMANOS": [
    "mão de obra", "salário", "salários", "encargo", 
    "encargos", "folha de pagamento", "remuneração",
    "diária", "funcionário", "colaborador"
],

"SERVIÇOS OPERACIONAIS": [
    "frete", "transporte", "carreto", "logística",
    "colheita", "secagem", "armazenagem", "pulverização", 
    "aplicação", "plantio", "preparo de solo"
],

"INFRAESTRUTURA E UTILIDADES": [
    "energia", "elétrica", "luz", "arrendamento", 
    "construção", "obra", "reforma", "cimento", "areia", 
    "brita", "tijolo", "telha", "madeira", "pintura"
],

"ADMINISTRATIVAS": [
    "honorário", "honorários", "contábil", "advocatício",
    "consultoria", "assessoria", "tarifa", "financeira",
    "juros", "multas", "cartório"
],

"SEGUROS E PROTEÇÃO": [
    "seguro", "apólice", "premio de seguro", "indenização"
],

"IMPOSTOS E TAXAS": [
    "itr", "iptu", "ipva", "incra", "ccir", "imposto",
    "impostos", "taxa", "taxas", "contribuição"
],

"INVESTIMENTOS": [
    "aquisição", "compra", "trator", "colheitadeira", 
    "veículo", "imóvel", "fazenda", "propriedade",
    "computador", "notebook", "laptop", "desktop", "pc",
    "servidor", "máquina", "implemento", "equipamento"
]


}

def classificar_nota_fiscal(dados):
    categorias = set()
    produtos = dados.get("itens") or dados.get("produtos") or []
    for produto in produtos:
        desc = produto.get("descricao", "").lower()
        for categoria, palavras in REGRAS_DE_CLASSIFICACAO.items():
            if any(p in desc for p in palavras):
                categorias.add(categoria)
    return list(categorias) if categorias else ["Outros"]

from datetime import datetime
from dateutil.relativedelta import relativedelta

def gerar_parcela_padrao(dados):
    if not dados.get("parcelas"):
        data_emissao = dados.get("dataEmissao") or dados.get("data_emissao")
        valor_total = dados.get("valorTotal") or dados.get("valor_total")
        if data_emissao and valor_total:
            try:
                # tenta converter em múltiplos formatos
                formatos = ["%Y-%m-%d", "%d/%m/%Y"]
                dt = None
                for fmt in formatos:
                    try:
                        dt = datetime.strptime(data_emissao, fmt)
                        break
                    except ValueError:
                        continue
                
                if dt is None:
                    raise ValueError(f"Formato de data inválido: {data_emissao}")

                vencimento = dt + relativedelta(months=1)
                dados["parcelas"] = [{
                    "dataVencimento": vencimento.strftime("%Y-%m-%d"),
                    "valorParcela": float(valor_total)
                }]
            except Exception as e:
                print(f"Erro ao gerar parcela padrão: {e}")

    return dados

# ---------------- Funções PDF ----------------
def extrair_texto_pdf(file_stream):
    try:
        doc = fitz.open(stream=file_stream.read(), filetype="pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
        if not texto.strip() and OCR_DISPONIVEL:
            texto = ""
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                texto += pytesseract.image_to_string(img)
        return texto
    except Exception as e:
        print(f"Erro ao extrair texto PDF: {e}")
        return ""

def extrair_dados_com_llm(texto):
    prompt = f"""
    Analise o texto da nota fiscal e retorne um JSON válido com:
    {{
        "fornecedor": {{
            "razaoSocial": "string",
            "fantasia": "string",
            "cnpj": "string"
        }},
        "faturado": {{
            "nomeCompleto": "string",
            "cpf": "string",
            "endereco": "string",
            "bairro": "string",
            "cep": "string"
        }},
        "numeroNotaFiscal": "string",
        "dataEmissao": "string",
        "valorTotal": 0.0,
        "protocoloAutorizacao": "string",
        "chaveAcesso": "string",
        "itens": [
            {{"descricao": "string", "quantidade": 0, "valorUnitario": 0.0}}
        ],
        "parcelas": []
    }}
    Se não houver valor, use null. Responda apenas JSON, sem explicações.
    Use null para campos que não existam na nota.
    Se não houver itens, retorne uma lista vazia.
    Se não houver parcelas, retorne uma lista vazia.
    Não inclua explicações ou qualquer texto extra.
    Valores numéricos devem ser retornados como números (não strings).
    Texto da Nota:
    {texto}
    """



    try:
        model = genai.GenerativeModel("gemini-1.5-flash", generation_config={"temperature": 0.0})
        response = model.generate_content(prompt)
        if response and response.candidates:
            return response.candidates[0].content.parts[0].text
        return None
    except Exception as e:
        print(f"Erro Gemini: {e}")
        return None

# ---------------- Rotas Flask ----------------
@app.route('/')
def index():
    return render_template('index.html', resultado_json=None, dados_formatados=None)

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
    os.makedirs('uploads', exist_ok=True)
    app.run(debug=True)
