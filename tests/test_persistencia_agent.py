"""Testes unitários para o PersistenciaAgent."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.AgentePersistencia.processador import PersistenciaAgent
from database.models import Base, Classificacao, MovimentoContas, ParcelasContas, Pessoas


@pytest.fixture()
def session_factory() -> sessionmaker:
    """Cria um SessionFactory isolado em banco SQLite em memória."""

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def agent(session_factory: sessionmaker) -> PersistenciaAgent:
    """Retorna o agente configurado com a SessionFactory de teste."""

    return PersistenciaAgent(session_factory=session_factory)


def _fetch_all(session: Session, model):
    return session.execute(select(model)).scalars().all()


def test_get_or_create_pessoa_cria_e_reaproveita(agent: PersistenciaAgent, session_factory: sessionmaker) -> None:
    dados = {"cnpj": "12.345.678/0001-00", "razaoSocial": "Fazenda Modelo"}

    primeiro_id = agent.get_or_create_pessoa(dados)
    segundo_id = agent.get_or_create_pessoa(dados)

    assert primeiro_id is not None
    assert primeiro_id == segundo_id

    with session_factory() as session:
        pessoas = _fetch_all(session, Pessoas)
        assert len(pessoas) == 1
        assert pessoas[0].documento == "12345678000100"


def test_get_or_create_classificacao_cria_e_reaproveita(agent: PersistenciaAgent, session_factory: sessionmaker) -> None:
    primeiro_id = agent.get_or_create_classificacao("Insumos")
    segundo_id = agent.get_or_create_classificacao({"descricao": "Insumos", "tipo": "DESPESA"})

    assert primeiro_id is not None
    assert primeiro_id == segundo_id

    with session_factory() as session:
        classificacoes = _fetch_all(session, Classificacao)
        assert len(classificacoes) == 1
        assert classificacoes[0].descricao == "Insumos"
        assert classificacoes[0].tipo == "DESPESA"


def test_lancar_conta_pagar_cria_movimento_parcelas_e_classificacao(
    agent: PersistenciaAgent,
    session_factory: sessionmaker,
) -> None:
    payload = {
        "fornecedor": {"razaoSocial": "Fazenda Modelo", "cnpj": "12.345.678/0001-00"},
        "faturado": {"nomeCompleto": "João da Silva", "cpf": "123.456.789-00"},
        "numeroNotaFiscal": "NF-001",
        "dataEmissao": "2024-02-10",
        "valorTotal": "1500,50",
        "classificacaoDespesa": ["Insumos"],
        "parcelas": [
            {"identificacao": "Parcela 1", "dataVencimento": "2024-03-10", "valorParcela": 750.25},
            {"identificacao": "Parcela 2", "dataVencimento": "2024-04-10", "valorParcela": 750.25},
        ],
    }

    resultado = agent.lancar_conta_pagar(payload)

    assert resultado["movimento_id"] is not None
    assert resultado["fornecedor_id"] is not None
    assert resultado["faturado_id"] is not None
    assert len(resultado["parcelas_ids"]) == 2
    assert len(resultado["classificacao_ids"]) == 1

    with session_factory() as session:
        movimento = session.get(MovimentoContas, resultado["movimento_id"])
        assert movimento is not None
        assert movimento.valor_total == Decimal("1500.50")
        assert movimento.fornecedor_id == resultado["fornecedor_id"]
        assert movimento.faturado_id == resultado["faturado_id"]

        parcelas = _fetch_all(session, ParcelasContas)
        assert len(parcelas) == 2
        assert {par.identificacao for par in parcelas} == {"Parcela 1", "Parcela 2"}

        classificacoes = _fetch_all(session, Classificacao)
        assert len(classificacoes) == 1
        assert classificacoes[0].descricao == "Insumos"