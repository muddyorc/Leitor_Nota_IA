# agents/consulta_rag/processador.py
from __future__ import annotations
from typing import Callable, Optional

import re
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased
from database.connection import SessionLocal
from config.settings import GOOGLE_API_KEY  # caso precise, mas usamos ia_service para gerar texto
from agents.AgentePersistencia.processador import PersistenciaAgent
import os

from database.models import Classificacao, MovimentoContas, Pessoas

# --- optional imports for semantic retrieval (only used if installed) ---
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except Exception:
    CHROMA_AVAILABLE = False

# Use your existing ia wrapper to call Gemini
from agents.AgenteExtracao.ia_service import responder_pergunta_com_llm  # Gemini wrapper adaptado para respostas textuais

_STOP_WORDS = {
    "qual",
    "quais",
    "que",
    "quanto",
    "quantos",
    "quando",
    "como",
    "para",
    "com",
    "dos",
    "das",
    "do",
    "da",
    "de",
    "nos",
    "nas",
    "uma",
    "um",
    "das",
    "dos",
    "as",
    "os",
    "notas",
    "nota",
    "valor",
    "foi",
    "foram",
    "recebidos",
    "recebido",
}
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
        self._llm_callable = llm_callable or responder_pergunta_com_llm

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

    @staticmethod
    def _format_currency(value) -> str:
        try:
            numeric = float(value or 0)
        except (TypeError, ValueError):
            numeric = 0.0
        formatted = f"R$ {numeric:,.2f}"
        return formatted.replace(",", "_").replace(".", ",").replace("_", ".")

    @staticmethod
    def _should_include_summary(pergunta: str | None) -> bool:
        if not pergunta:
            return False
        termos_chave = ("custo", "gasto", "despesa", "recorr", "combust", "manut", "significativo")
        pergunta_lower = pergunta.lower()
        return any(chave in pergunta_lower for chave in termos_chave)

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

    def _get_or_create_collection(self):
        if not self._enable_chroma or self._chroma_client is None:
            return None
        try:
            return self._chroma_client.get_collection("movimentos")
        except Exception:
            try:
                return self._chroma_client.create_collection("movimentos")
            except Exception:
                return None

    def _build_summary_context(self, session: Session, limite: int = 5) -> str:
        resumo_partes: list[str] = []

        classificacao_totais = (
            session.query(Classificacao.descricao, func.sum(MovimentoContas.valor_total).label("total"))
            .join(Classificacao.movimentos)
            .group_by(Classificacao.descricao)
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .limit(limite)
            .all()
        )
        if classificacao_totais:
            linhas = [
                f"- {descricao or 'Sem classificacao'}: {self._format_currency(total)}"
                for descricao, total in classificacao_totais
                if total is not None
            ]
            if linhas:
                resumo_partes.append("Classificacoes com maiores gastos:\n" + "\n".join(linhas))

        fornecedor_totais = (
            session.query(Pessoas.razaosocial, func.sum(MovimentoContas.valor_total).label("total"))
            .join(MovimentoContas, MovimentoContas.fornecedor_id == Pessoas.id)
            .group_by(Pessoas.razaosocial)
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .limit(limite)
            .all()
        )
        if fornecedor_totais:
            linhas = [
                f"- {nome or 'Fornecedor nao informado'}: {self._format_currency(total)}"
                for nome, total in fornecedor_totais
                if total is not None
            ]
            if linhas:
                resumo_partes.append("Fornecedores mais onerosos:\n" + "\n".join(linhas))

        recorrentes = (
            session.query(
                MovimentoContas.descricao,
                func.count(MovimentoContas.id).label("freq"),
                func.sum(MovimentoContas.valor_total).label("total"),
            )
            .group_by(MovimentoContas.descricao)
            .having(func.count(MovimentoContas.id) > 1)
            .order_by(func.count(MovimentoContas.id).desc(), func.sum(MovimentoContas.valor_total).desc())
            .limit(limite)
            .all()
        )
        if recorrentes:
            linhas = [
                f"- {descricao or 'Descricao nao informada'}: {freq} ocorrencias somando {self._format_currency(total)}"
                for descricao, freq, total in recorrentes
                if total is not None
            ]
            if linhas:
                resumo_partes.append("Gastos recorrentes detectados:\n" + "\n".join(linhas))

        return "\n\n".join(resumo_partes)

    # ---------------- RAG Simples ----------------
    def _retrieve_data_simples(self, pergunta: str, limit: int = 10) -> str:
        """Executa uma query SQL direta e retorna um contexto textual"""
        session: Session = self._session_factory()
        try:
            fornecedor_alias = aliased(Pessoas)
            faturado_alias = aliased(Pessoas)
            class_alias = aliased(Classificacao)

            base_stmt = (
                select(MovimentoContas)
                .outerjoin(fornecedor_alias, MovimentoContas.fornecedor)
                .outerjoin(faturado_alias, MovimentoContas.faturado)
                .outerjoin(class_alias, MovimentoContas.classificacoes)
            )

            tokens_raw = re.findall(r"\b\w{3,}\b", pergunta.lower()) if pergunta else []
            tokens = []
            for token in tokens_raw:
                if token in _STOP_WORDS or token in tokens:
                    continue
                tokens.append(token)
            filters = []
            for token in tokens[:5]:  # limita tokens relevantes para evitar filtros excessivos
                pattern = f"%{token}%"
                filters.extend(
                    [
                        MovimentoContas.descricao.ilike(pattern),
                        MovimentoContas.numero_nota_fiscal.ilike(pattern),
                        fornecedor_alias.razaosocial.ilike(pattern),
                        fornecedor_alias.fantasia.ilike(pattern),
                        faturado_alias.razaosocial.ilike(pattern),
                        faturado_alias.fantasia.ilike(pattern),
                        class_alias.descricao.ilike(pattern),
                    ]
                )

            stmt = base_stmt
            if filters:
                stmt = stmt.where(or_(*filters))

            stmt = stmt.order_by(MovimentoContas.data_emissao.desc()).limit(limit)
            rows = session.execute(stmt).scalars().unique().all()

            if not rows and filters:
                fallback_stmt = base_stmt.order_by(MovimentoContas.data_emissao.desc()).limit(limit)
                rows = session.execute(fallback_stmt).scalars().unique().all()

            resumo_texto = ""
            if self._should_include_summary(pergunta):
                resumo_texto = self._build_summary_context(session)

            partes = []
            for movimento in rows:
                fornecedor = None
                faturado = None
                if movimento.fornecedor:
                    fornecedor = movimento.fornecedor.razaosocial or movimento.fornecedor.fantasia
                if movimento.faturado:
                    faturado = movimento.faturado.razaosocial or movimento.faturado.fantasia

                classificacoes = [c.descricao for c in movimento.classificacoes or [] if c.descricao]
                classificacao_texto = ", ".join(classificacoes) if classificacoes else None

                partes.append(
                    "Movimento "
                    f"{movimento.id}: nota {movimento.numero_nota_fiscal}, "
                    f"data {movimento.data_emissao}, valor {movimento.valor_total}, descricao: {movimento.descricao}"
                    + (f", fornecedor: {fornecedor}" if fornecedor else "")
                    + (f", faturado: {faturado}" if faturado else "")
                    + (f", classificações: {classificacao_texto}" if classificacao_texto else "")
                )
            contexto = "\n".join(partes) or "Nenhum registro encontrado."
            if resumo_texto:
                if contexto and contexto != "Nenhum registro encontrado.":
                    contexto = f"{contexto}\n\nResumo financeiro:\n{resumo_texto}"
                else:
                    contexto = f"Resumo financeiro:\n{resumo_texto}"
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
        # Reutiliza a função de consulta ao Gemini configurada para respostas textuais.
        resposta = self._llm_callable(prompt)
        return resposta or "Falha ao gerar resposta via LLM."

    # ---------------- RAG Semântico ----------------
    def _retrieve_data_semantico(self, pergunta: str, k: int = 3) -> str:
        if not self._enable_chroma or self._chroma_client is None or self._embed_model is None:
            return "ChromaDB ou model de embeddings não configurado."
        query_emb = self._embed_model.encode([pergunta])[0].tolist()
        # Ensure the semantic collection exists and has data before querying embeddings.
        collection = self._get_or_create_collection()
        if collection is None:
            return "Coleção Chroma 'movimentos' não encontrada."

        try:
            total_docs = collection.count()
        except Exception:
            total_docs = 0

        if total_docs == 0:
            try:
                self.indexar_movimentos_para_chroma()
                collection = self._get_or_create_collection()
            except Exception:
                collection = None

            if collection is None:
                return self._retrieve_data_simples(pergunta)

            try:
                total_docs = collection.count()
            except Exception:
                total_docs = 0

        results = collection.query(query_embeddings=[query_emb], n_results=k, include=['metadatas', 'documents'])
        docs = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        if not docs:
            return self._retrieve_data_simples(pergunta)

        partes = []
        for i, doc in enumerate(docs):
            meta = metadatas[i] if i < len(metadatas) else {}
            partes.append(f"Documento {i+1} (id={meta.get('id')}): {doc}")

        if not partes:
            return self._retrieve_data_simples(pergunta)

        contexto_semantico = "\n".join(partes)

        # Complementa com busca simples para enriquecer contexto e evitar respostas vazias
        contexto_simples = self._retrieve_data_simples(pergunta)
        if contexto_simples and contexto_simples.strip() and contexto_simples.strip() != "Nenhum registro encontrado.":
            return f"{contexto_semantico}\n\nContexto adicional (SQL):\n{contexto_simples}"

        return contexto_semantico

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
                fornecedor = None
                faturado = None
                if movimento.fornecedor:
                    fornecedor = movimento.fornecedor.razaosocial or movimento.fornecedor.fantasia
                if movimento.faturado:
                    faturado = movimento.faturado.razaosocial or movimento.faturado.fantasia

                classificacoes = [c.descricao for c in movimento.classificacoes or [] if c.descricao]
                classificacao_texto = ", ".join(classificacoes) if classificacoes else "Sem classificação"

                texto = (
                    "Movimento "
                    f"{movimento.id}: nota {movimento.numero_nota_fiscal or 'N/A'}, "
                    f"emitida em {movimento.data_emissao}, valor total {movimento.valor_total}, "
                    f"descricao: {movimento.descricao or 'Sem descrição'}, "
                    f"fornecedor: {fornecedor or 'Não informado'}, "
                    f"faturado: {faturado or 'Não informado'}, "
                    f"classificação: {classificacao_texto}"
                )
                docs.append(texto)
                ids.append(str(movimento.id))
                metadatas.append({"id": movimento.id})
            collection = self._get_or_create_collection()
            if collection is None:
                raise RuntimeError("Coleção Chroma 'movimentos' não encontrada.")
            if not docs:
                return {"indexed": 0}
            embs = self._embed_model.encode(docs).tolist()
            add_fn = getattr(collection, "upsert", collection.add)
            add_fn(documents=docs, embeddings=embs, ids=ids, metadatas=metadatas)

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
