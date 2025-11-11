# scripts/indexar_dados.py
"""Script utilitário para (re)indexar movimentos no ChromaDB."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.consulta_rag.processador import ConsultaRagAgent  # noqa: E402


def main() -> int:
    try:
        agent = ConsultaRagAgent()
        result = agent.indexar_movimentos_para_chroma()
        print("Indexação finalizada:", result)
        return 0
    except RuntimeError as exc:
        print(f"Indexação RAG não executada: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
