"""Cobertura para o script database.init_db.create_tables."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import database.init_db as init_db  # noqa: E402
from database.models import Base  # noqa: E402


@pytest.fixture()
def temp_engine(tmp_path):
    """Engine SQLite persistida em arquivo temporário para inspeção posterior."""

    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_file}", future=True)
    yield engine
    engine.dispose()


def test_create_tables_cria_schema(monkeypatch, temp_engine):
    monkeypatch.setattr(init_db, "engine", temp_engine)

    init_db.create_tables()

    inspector = inspect(temp_engine)
    tabelas = set(inspector.get_table_names())
    esperado = {
        "pessoas",
        "classificacao",
        "movimento_contas",
        "parcelas_contas",
        "MovimentoContas_has_Classificacao",
    }
    assert esperado.issubset(tabelas)


def test_create_tables_trata_operational_error(monkeypatch, capsys):
    def _raise_operational_error(*_args, **_kwargs):
        raise OperationalError("falha", None, None)

    monkeypatch.setattr(init_db.Base.metadata, "create_all", _raise_operational_error, raising=False)

    init_db.create_tables()

    captured = capsys.readouterr()
    assert "Falha ao conectar ao banco de dados" in captured.out
    assert "Verifique se o serviço PostgreSQL" in captured.out