"""Utility script to create database tables defined in the ORM models."""

from __future__ import annotations

from sqlalchemy.exc import OperationalError

from .connection import Base, engine
import database.models  # noqa: F401 - ensure models are imported before create_all


def create_tables() -> None:
    """Create all tables in the configured database."""
    try:
        Base.metadata.create_all(bind=engine)
        print("Tabelas criadas com sucesso.")
    except OperationalError as exc:
        # Provide an actionable message when the DB service is offline
        print("Falha ao conectar ao banco de dados:", exc)
        print("Verifique se o serviço PostgreSQL está em execução e os parâmetros de conexão estão corretos.")


if __name__ == "__main__":
    create_tables()
