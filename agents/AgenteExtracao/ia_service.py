import textwrap

import google.generativeai as genai

from config.settings import GOOGLE_API_KEY, REGRAS_DE_CLASSIFICACAO

genai.configure(api_key=GOOGLE_API_KEY)


def extrair_dados_com_llm(texto):
    categorias_prompt = "\n".join(
        f"- {categoria}: palavras associadas -> {', '.join(palavras)}"
        for categoria, palavras in REGRAS_DE_CLASSIFICACAO.items()
    )

    prompt = textwrap.dedent(
        f"""
        Você é um analista financeiro júnior responsável por revisar documentos fiscais rurais.
        Analise o texto fornecido e produza APENAS um JSON válido seguindo os requisitos abaixo.

        Categorias de despesa disponíveis:
        {categorias_prompt}

        Regras de saída:
        - Use null para campos ausentes ou quando o valor não estiver explícito.
        - Preencha números como valores numéricos (sem aspas) e datas no formato ISO yyyy-mm-dd sempre que possível.
        - "classificacaoDespesa" deve ser um array com pelo menos uma das categorias listadas acima; se nada se aplicar, retorne ["Outros"].
        - Não utilize blocos de código ou qualquer texto adicional fora do JSON final.

        Estrutura esperada do JSON:
        {{
            "fornecedor": {{"razaoSocial": null, "fantasia": null, "cnpj": null}},
            "faturado": {{"nomeCompleto": null, "cpf": null, "endereco": null, "bairro": null, "cep": null}},
            "numeroNotaFiscal": null,
            "dataEmissao": null,
            "valorTotal": null,
            "protocoloAutorizacao": null,
            "chaveAcesso": null,
            "itens": [{{"descricao": null, "quantidade": null, "valorUnitario": null}}],
            "parcelas": [],
            "classificacaoDespesa": ["string"]
        }}

        Texto da nota fiscal:
        {texto}
        """
    )
    try:
        model = genai.GenerativeModel("gemini-2.5-flash-lite", generation_config={"temperature": 0.0})
        response = model.generate_content(prompt)
        if response and response.candidates:
            return response.candidates[0].content.parts[0].text
        return None
    except Exception as e:
        print(f"Erro Gemini: {e}")
        return None
