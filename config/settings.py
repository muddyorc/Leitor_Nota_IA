import os
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

UPLOAD_FOLDER = 'uploads'

REGRAS_DE_CLASSIFICACAO = {
    "INSUMOS AGRÍCOLAS": ["semente", "sementes", "fertilizante", "fertilizantes", "defensivo", "defensivos", "agrotóxico", "herbicida","inseticida","fungicida","adubo","corretivo","calcário"],
    "MANUTENÇÃO E OPERAÇÃO": ["combustível","diesel","gasolina","etanol","óleo","graxa","lubrificante","peça","peças","parafuso","rolamento","retentor","embreagem","manutenção","reparo","conserto","pneu","filtro","correia","ferramenta","bateria"],
    "RECURSOS HUMANOS": ["mão de obra","salário","salários","encargo","encargos","folha de pagamento","remuneração","diária","funcionário","colaborador"],
    "SERVIÇOS OPERACIONAIS": ["frete","transporte","carreto","logística","colheita","secagem","armazenagem","pulverização","aplicação","plantio","preparo de solo"],
    "INFRAESTRUTURA E UTILIDADES": ["energia","elétrica","luz","arrendamento","construção","obra","reforma","cimento","areia","brita","tijolo","telha","madeira","pintura"],
    "ADMINISTRATIVAS": ["honorário","honorários","contábil","advocatício","consultoria","assessoria","tarifa","financeira","juros","multas","cartório"],
    "SEGUROS E PROTEÇÃO": ["seguro","apólice","premio de seguro","indenização"],
    "IMPOSTOS E TAXAS": ["itr","iptu","ipva","incra","ccir","imposto","impostos","taxa","taxas","contribuição"],
    "INVESTIMENTOS": ["aquisição","compra","trator","colheitadeira","veículo","imóvel","fazenda","propriedade","computador","notebook","laptop","desktop","pc","servidor","máquina","implemento","equipamento"]
}
