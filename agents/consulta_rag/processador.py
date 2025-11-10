# agents/consulta_rag/processador.py
from __future__ import annotations
from typing import Optional, List
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from config.settings import GOOGLE_API_KEY  # caso precise, mas usamos ia_service para gerar texto
from agents.AgentePersistencia.processador import PersistenciaAgent
import os

# --- optional imports for semantic retrieval (only used if installed) ---
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except Exception:
    CHROMA_AVAILABLE = False

# Use your existing ia wrapper to call Gemini
from agents.AgenteExtracao.ia_service import extrair_dados_com_llm  # we will call Gemini via a simpler wrapper
# If you have a dedicated function for prompting Gemini, prefer that. Here we reuse ia_service as it exists. :contentReference[oaicite:4]{index=4}

class ConsultaRagAgent:
    def __init__(self, session_factory: callable = SessionLocal, chroma_dir: str | None = None):
        self._session_factory = session_factory
        self.persist_agent = PersistenciaAgent(session_factory)  # for schema knowledge if needed
        self.chroma_dir = chroma_dir or os.getenv("CHROMA_DIR", "./_chromadb")
        self._chroma_client = None
        self._embed_model = None
        if CHROMA_AVAILABLE:
            self._init_chroma()

    def _init_chroma(self):
        # initializes chroma client and embedder if available
        if not CHROMA_AVAILABLE:
            return
        self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        self._chroma_client = chromadb.Client(ChromaSettings(chroma_db_impl="duckdb+parquet", persist_directory=self.chroma_dir))

    # ---------------- RAG Simples ----------------
    def _retrieve_data_simples(self, pergunta: str, limit: int = 10) -> str:
        """Executa uma query SQL direta e retorna um contexto textual"""
        session: Session = self._session_factory()
        try:
            # *** Heurística simples: tenta identificar palavras-chave na pergunta para filtrar tipo/data/fornecedor ***
            sql = text("""
                SELECT id, numero_nota_fiscal, data_emissao, descricao, valor_total, fornecedor_id
                FROM movimento_contas
                ORDER BY data_emissao DESC
                LIMIT :limit
            """)
            # NOTE: personalize conforme sua modelagem (nomes de colunas/tabela). A tabela usada no seu projeto parece ser MovimentoContas -> movimento_contas.
            rows = session.execute(sql, {"limit": limit}).mappings().all()
            partes = []
            for r in rows:
                partes.append(f"Movimento {r['id']}: nota {r['numero_nota_fiscal']}, data {r['data_emissao']}, valor {r['valor_total']}, descricao: {r['descricao']}")
            contexto = "\n".join(partes) or "Nenhum registro encontrado."
            return contexto
        finally:
            session.close()

    def executar_consulta_simples(self, pergunta: str) -> str:
        contexto = self._retrieve_data_simples(pergunta)
        prompt = (
            f"Você é um analista financeiro. Com base **apenas** nos seguintes dados do sistema:\n\n"
            f"{contexto}\n\n"
            f"Responda a seguinte pergunta do usuário: {pergunta}\n\n"
            f"Se os dados não forem suficientes, informe que a resposta não pode ser encontrada."
        )
        # Reutiliza sua função que chama Gemini (ela retorna texto). :contentReference[oaicite:5]{index=5}
        # Aqui supomos que extrair_dados_com_llm retorna texto. Para prompts de consulta é preferível ter outra função,
        # mas usamos a existente para manter compatibilidade; adapte se tiver wrapper específico.
        resposta = extrair_dados_com_llm(prompt)
        return resposta or "Falha ao gerar resposta via LLM."

    # ---------------- RAG Semântico ----------------
    def _retrieve_data_semantico(self, pergunta: str, k: int = 3) -> str:
        if not CHROMA_AVAILABLE or self._chroma_client is None or self._embed_model is None:
            return "ChromaDB ou model de embeddings não configurado."
        query_emb = self._embed_model.encode([pergunta])[0].tolist()
        collection = None
        try:
            collection = self._chroma_client.get_collection("movimentos")
        except Exception:
            # tentativa de fallback
            try:
                collection = self._chroma_client.create_collection("movimentos")
            except Exception:
                return "Coleção Chroma 'movimentos' não encontrada."
        results = collection.query(query_embeddings=[query_emb], n_results=k, include=['metadatas', 'documents', 'ids'])
        docs = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        partes = []
        for i, doc in enumerate(docs):
            meta = metadatas[i] if i < len(metadatas) else {}
            partes.append(f"Documento {i+1} (id={meta.get('id')}): {doc}")
        return "\n".join(partes) or "Nenhum documento vetorial encontrado."

    def executar_consulta_semantica(self, pergunta: str) -> str:
        contexto = self._retrieve_data_semantico(pergunta)
        prompt = (
            f"Você é um analista financeiro. Com base **apenas** nos seguintes dados do sistema:\n\n"
            f"{contexto}\n\n"
            f"Responda a seguinte pergunta do usuário: {pergunta}\n\n"
            f"Se os dados não forem suficientes, informe que a resposta não pode ser encontrada."
        )
        resposta = extrair_dados_com_llm(prompt)
        return resposta or "Falha ao gerar resposta via LLM."

    # ---------------- Index script helper (opcional) ----------------
    def indexar_movimentos_para_chroma(self, k_batch: int = 1000):
        """Varredura do banco para indexar textos no ChromaDB (executar manualmente)."""
        if not CHROMA_AVAILABLE or self._chroma_client is None or self._embed_model is None:
            raise RuntimeError("ChromaDB ou sentence-transformers não disponíveis no ambiente.")
        session = self._session_factory()
        try:
            sql = text("SELECT id, numero_nota_fiscal, data_emissao, descricao, valor_total, fornecedor_id FROM movimento_contas")
            rows = session.execute(sql).mappings().all()
            docs = []
            ids = []
            metadatas = []
            for r in rows:
                texto = f"Movimento {r['id']}: nota {r['numero_nota_fiscal']}, data {r['data_emissao']}, valor {r['valor_total']}, descricao: {r['descricao']}"
                docs.append(texto)
                ids.append(str(r['id']))
                metadatas.append({"id": r['id']})
            collection = None
            try:
                collection = self._chroma_client.get_collection("movimentos")
            except Exception:
                collection = self._chroma_client.create_collection("movimentos")
            embs = self._embed_model.encode(docs).tolist()
            collection.add(documents=docs, embeddings=embs, ids=ids, metadatas=metadatas)
            self._chroma_client.persist()
            return {"indexed": len(docs)}
        finally:
            session.close()
