"""Testes para o endpoint /upload garantindo persistência e resposta."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app  # noqa: E402
from agents.AgentePersistencia.processador import PersistenciaAgent  # noqa: E402
from database.models import Base, Classificacao, MovimentoContas, ParcelasContas, Pessoas  # noqa: E402


@pytest.fixture()
def app_client(monkeypatch):
    """Configura o app Flask com dependências simuladas e banco em memória."""

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    test_agent = PersistenciaAgent(session_factory=session_factory)

    monkeypatch.setattr("app.persistencia_agent", test_agent)

    sample_payload = {
        "fornecedor": {"razaoSocial": "Fazenda Modelo", "cnpj": "12.345.678/0001-00"},
        "faturado": {"nomeCompleto": "João da Silva", "cpf": "123.456.789-00"},
        "numeroNotaFiscal": "NF-123",
        "dataEmissao": "2024-05-01",
        "valorTotal": "2500,00",
        "classificacaoDespesa": ["Insumos"],
        "parcelas": [
            {"identificacao": "Parcela Única", "dataVencimento": "2024-06-01", "valorParcela": "2500,00"}
        ],
    }

    monkeypatch.setattr("app.extrair_texto_pdf", lambda _: "texto fake")
    monkeypatch.setattr("app.extrair_dados_com_llm", lambda _texto: json.dumps(sample_payload))

    client = app.test_client()

    yield client, session_factory, sample_payload

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_upload_endpoint_persistencia_sucesso(app_client):
    client, session_factory, payload = app_client

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake pdf"), "nota.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200

    body = response.get_json()
    assert body is not None
    assert body["numeroNotaFiscal"] == payload["numeroNotaFiscal"]
    assert "_persistencia" in body

    resumo = body["_persistencia"]
    assert resumo["movimento_id"] is not None
    assert len(resumo["parcelas_ids"]) == 1

    with session_factory() as session:
        movimentos = session.execute(select(MovimentoContas)).scalars().all()
        assert len(movimentos) == 1
        assert movimentos[0].numero_nota_fiscal == payload["numeroNotaFiscal"]

        pessoas = session.execute(select(Pessoas)).scalars().all()
        assert len(pessoas) == 2

        parcelas = session.execute(select(ParcelasContas)).scalars().all()
        assert len(parcelas) == 1

    classificacoes = session.execute(select(Classificacao)).scalars().all()
    assert len(classificacoes) == 1


def test_upload_sem_arquivo_retorna_400(app_client):
    client, *_ = app_client

    response = client.post("/upload", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Nenhum arquivo enviado"


def test_upload_formato_invalido_retorna_400(app_client):
    client, *_ = app_client

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake"), "nota.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Arquivo inválido"


def test_upload_falha_extracao_pdf_retorna_500(app_client, monkeypatch):
    client, *_ = app_client
    monkeypatch.setattr("app.extrair_texto_pdf", lambda _stream: "")

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake pdf"), "nota.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "Não foi possível extrair texto do PDF"


def test_upload_falha_gemini_retorna_500(app_client, monkeypatch):
    client, *_ = app_client
    monkeypatch.setattr("app.extrair_dados_com_llm", lambda _texto: None)

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake pdf"), "nota.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    assert response.get_json()["error"] == "Falha na comunicação com Gemini"


def test_upload_json_invalido_retorna_500(app_client, monkeypatch):
    client, *_ = app_client
    monkeypatch.setattr("app.extrair_dados_com_llm", lambda _texto: "{invalido")

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake pdf"), "nota.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "JSON inválido retornado pelo modelo"
    assert body["resposta"] == "{invalido"


def test_upload_falha_persistencia_retorna_500(app_client, monkeypatch):
    client, _, _ = app_client

    class FakeAgent:
        def lancar_conta_pagar(self, _dados):
            raise RuntimeError("falha test")

    monkeypatch.setattr("app.persistencia_agent", FakeAgent())

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"fake pdf"), "nota.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "Falha ao persistir dados"
    assert "falha test" in body["detalhes"]

    # O monkeypatch restaura o agente original automaticamente após o teste