from datetime import datetime
from dateutil.relativedelta import relativedelta


def gerar_parcela_padrao(dados):
    if not dados.get("parcelas"):
        data_emissao = dados.get("dataEmissao") or dados.get("data_emissao")
        valor_total = dados.get("valorTotal") or dados.get("valor_total")
        if data_emissao and valor_total:
            formatos = ["%Y-%m-%d", "%d/%m/%Y"]
            dt = None
            for fmt in formatos:
                try:
                    dt = datetime.strptime(data_emissao, fmt)
                    break
                except ValueError:
                    continue
            if dt:
                vencimento = dt + relativedelta(months=1)
                dados["parcelas"] = [{
                    "dataVencimento": vencimento.strftime("%Y-%m-%d"),
                    "valorParcela": float(valor_total)
                }]
    return dados
