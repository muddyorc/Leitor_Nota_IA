import google.generativeai as genai
from config.settings import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)

def extrair_dados_com_llm(texto):
    prompt = f"""
    Analise o texto da nota fiscal e retorne um JSON válido com:
    {{
        "fornecedor": {{"razaoSocial": "string","fantasia": "string","cnpj": "string"}},
        "faturado": {{"nomeCompleto": "string","cpf": "string","endereco": "string","bairro": "string","cep": "string"}},
        "numeroNotaFiscal": "string",
        "dataEmissao": "string",
        "valorTotal": 0.0,
        "protocoloAutorizacao": "string",
        "chaveAcesso": "string",
        "itens": [{{"descricao": "string","quantidade": 0,"valorUnitario": 0.0}}],
        "parcelas": []
    }}
    Se não houver valor, use null. Responda apenas JSON, sem explicações.
    Use null para campos que não existam na nota.
    Texto da Nota:
    {texto}
    """
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite", generation_config={"temperature": 0.0})
        response = model.generate_content(prompt)
        if response and response.candidates:
            return response.candidates[0].content.parts[0].text
        return None
    except Exception as e:
        print(f"Erro Gemini: {e}")
        return None
