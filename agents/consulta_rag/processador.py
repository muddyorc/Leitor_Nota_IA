# agents/consulta_rag/processador.py
from __future__ import annotations
from typing import Callable, Optional

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from config.settings import GOOGLE_API_KEY  # caso precise, mas usamos ia_service para gerar texto
from agents.AgentePersistencia.processador import PersistenciaAgent
import os

from database.models import MovimentoContas

# --- optional imports for semantic retrieval (only used if installed) ---
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except Exception:
    CHROMA_AVAILABLE = False

# Use your existing ia wrapper to call Gemini
from agents.AgenteExtracao.ia_service import extrair_dados_com_llm  # we will call Gemini via a simpler wrapper
# If you have a dedicated function for prompting Gemini, prefer that. Here we reuse ia_service as it exists. :contentReference[oaicite:4]{index=4}

class ConsultaRagAgent:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        chroma_dir: str | None = None,
        llm_callable: Optional[Callable[[str], str]] = None,
        chroma_client=None,
        embed_model=None,
        enable_chroma: bool | None = None,
    ):
        self._session_factory = session_factory
        self.persist_agent = PersistenciaAgent(session_factory)
        self.chroma_dir = chroma_dir or os.getenv("CHROMA_DIR", "./_chromadb")
        self._chroma_client = chroma_client
        self._embed_model = embed_model
        self._llm_callable = llm_callable or extrair_dados_com_llm

        if enable_chroma is None:
            enable_chroma = CHROMA_AVAILABLE
        self._enable_chroma = bool(enable_chroma and CHROMA_AVAILABLE)

        if self._enable_chroma and (self._chroma_client is None or self._embed_model is None):
            try:
                self._init_chroma()
            except Exception as exc:  # noqa: BLE001 - queremos sobreviver em ambiente sem Chroma
                print(f"ChromaDB desabilitado: {exc}")
                self._enable_chroma = False
                self._chroma_client = None
                self._embed_model = None

    def _init_chroma(self):
        # initializes chroma client and embedder if available
        if not self._enable_chroma:
            return

        persist_path = Path(self.chroma_dir).resolve()
        persist_path.mkdir(parents=True, exist_ok=True)

        if self._embed_model is None:
            self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")

        persistent_client_cls = getattr(chromadb, "PersistentClient", None)
        if persistent_client_cls is not None:
            self._chroma_client = persistent_client_cls(path=str(persist_path))
        else:
            from chromadb.config import Settings as ChromaSettings  # type: ignore[import]

            self._chroma_client = chromadb.Client(
                ChromaSettings(chroma_db_impl="duckdb+parquet", persist_directory=str(persist_path))
            )

    # ---------------- RAG Simples ----------------
    def _retrieve_data_simples(self, pergunta: str, limit: int = 10) -> str:
        """Executa uma query SQL direta e retorna um contexto textual"""
        session: Session = self._session_factory()
        try:
            rows = (
                session.execute(
                    select(MovimentoContas).order_by(MovimentoContas.data_emissao.desc()).limit(limit)
                )
                .scalars()
                .all()
            )
            partes = []
            for movimento in rows:
                partes.append(
                    "Movimento "
                    f"{movimento.id}: nota {movimento.numero_nota_fiscal}, "
                    f"data {movimento.data_emissao}, valor {movimento.valor_total}, descricao: {movimento.descricao}"
                )
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
        resposta = self._llm_callable(prompt)
        return resposta or "Falha ao gerar resposta via LLM."

    # ---------------- RAG Semântico ----------------
    def _retrieve_data_semantico(self, pergunta: str, k: int = 3) -> str:
        if not self._enable_chroma or self._chroma_client is None or self._embed_model is None:
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
        resposta = self._llm_callable(prompt)
        return resposta or "Falha ao gerar resposta via LLM."

    # ---------------- Index script helper (opcional) ----------------
    def indexar_movimentos_para_chroma(self, k_batch: int = 1000):
        """Varredura do banco para indexar textos no ChromaDB (executar manualmente)."""
        if not self._enable_chroma or self._chroma_client is None or self._embed_model is None:
            raise RuntimeError("ChromaDB ou sentence-transformers não disponíveis no ambiente.")
        session = self._session_factory()
        try:
            rows = session.execute(select(MovimentoContas)).scalars().all()
            docs = []
            ids = []
            metadatas = []
            for movimento in rows:
                texto = (
                    "Movimento "
                    f"{movimento.id}: nota {movimento.numero_nota_fiscal}, "
                    f"data {movimento.data_emissao}, valor {movimento.valor_total}, descricao: {movimento.descricao}"
                )
                docs.append(texto)
                ids.append(str(movimento.id))
                metadatas.append({"id": movimento.id})
            collection = None
            try:
                collection = self._chroma_client.get_collection("movimentos")
            except Exception:
                collection = self._chroma_client.create_collection("movimentos")
            embs = self._embed_model.encode(docs).tolist()
            collection.add(documents=docs, embeddings=embs, ids=ids, metadatas=metadatas)

            if hasattr(self._chroma_client, "persist"):
                self._chroma_client.persist()
            return {"indexed": len(docs)}
        finally:
            session.close()

    # --- métodos auxiliares para compatibilidade com testes antigos ---
    def consultar_simples(self, pergunta: str):
        return self.executar_consulta_simples(pergunta)

    def consultar_semantico(self, pergunta: str):
        return self.executar_consulta_semantica(pergunta)

    def indexar_movimentos(self):
        return self.indexar_movimentos_para_chroma()
