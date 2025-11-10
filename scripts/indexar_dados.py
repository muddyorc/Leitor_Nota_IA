# scripts/indexar_dados.py
from agents.consulta_rag.processador import ConsultaRagAgent

def main():
    agent = ConsultaRagAgent()
    result = agent.indexar_movimentos_para_chroma()
    print("Indexação finalizada:", result)

if __name__ == "__main__":
    main()
