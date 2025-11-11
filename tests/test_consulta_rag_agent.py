import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.consulta_rag.processador import ConsultaRagAgent  # noqa: E402
from database.models import Base, MovimentoContas  # noqa: E402


@pytest.fixture()
def session_factory():
    """SessionFactory isolada em SQLite para validar interações do agente."""

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def agente_sem_chroma(session_factory):
    """Agent configurado com LLM mockado e Chroma desabilitado."""

    llm_mock = MagicMock(return_value="resposta sintetizada")
    agent = ConsultaRagAgent(session_factory=session_factory, llm_callable=llm_mock, enable_chroma=False)
    return agent, llm_mock


def test_executar_consulta_simples_utiliza_contexto(session_factory, agente_sem_chroma, monkeypatch):
    agent, llm_mock = agente_sem_chroma

    monkeypatch.setattr(agent, "_retrieve_data_simples", lambda *_args, **_kwargs: "contexto relevante")

    resposta = agent.executar_consulta_simples("Qual o último movimento?")

    llm_mock.assert_called_once()
    prompt = llm_mock.call_args.args[0]
    assert "contexto relevante" in prompt
    assert "Qual o último movimento?" in prompt
    assert resposta == "resposta sintetizada"


def test_executar_consulta_semantica_sem_chroma_indica_indisponibilidade(session_factory):
    agent = ConsultaRagAgent(
        session_factory=session_factory,
        llm_callable=lambda prompt: prompt,
        enable_chroma=False,
    )

    prompt = agent.executar_consulta_semantica("Pergunta qualquer?")

    assert "ChromaDB ou model de embeddings não configurado" in prompt
    assert "Pergunta qualquer?" in prompt


class _FakeEmbeddingModel:
    def __init__(self, vector=None):
        self._vector = vector or [0.1, 0.2, 0.3]

    class _VectorWrapper(list):
        def tolist(self):
            return list(self)

    def encode(self, docs):
        return self._VectorWrapper([list(self._vector) for _ in docs])


class _FakeCollection:
    def __init__(self):
        self.add_kwargs = None

    def add(self, **kwargs):
        self.add_kwargs = kwargs


class _FakeChromaClient:
    def __init__(self, collection):
        self._collection = collection
        self.persist_called = False

    def get_collection(self, _name):
        return self._collection

    def create_collection(self, _name):
        return self._collection

    def persist(self):
        self.persist_called = True


@pytest.fixture()
def movimento_cadastrado(session_factory):
    with session_factory() as session:
        movimento = MovimentoContas(
            descricao="Compra de ingresso para jogo",
            valor_total=Decimal("200.00"),
            numero_nota_fiscal="NF-1",
        )
        session.add(movimento)
        session.commit()


def test_indexar_movimentos_para_chroma_inclui_documentos(session_factory, movimento_cadastrado):
    collection = _FakeCollection()
    chroma_client = _FakeChromaClient(collection)
    embed_model = _FakeEmbeddingModel([0.1, 0.2, 0.3])

    agent = ConsultaRagAgent(
        session_factory=session_factory,
        llm_callable=lambda prompt: prompt,
        chroma_client=chroma_client,
        embed_model=embed_model,
        enable_chroma=True,
    )

    resultado = agent.indexar_movimentos_para_chroma()

    assert resultado == {"indexed": 1}
    assert collection.add_kwargs is not None
    assert collection.add_kwargs["metadatas"][0]["id"] == 1
    assert chroma_client.persist_called is True
