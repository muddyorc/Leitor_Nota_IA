"""Utility helper to wait until the PostgreSQL database is ready."""

from __future__ import annotations

import os
import sys
import time
from typing import Iterable

from dotenv import load_dotenv
from psycopg2 import OperationalError
import psycopg2

load_dotenv()


def _connection_params() -> dict[str, str]:
    """Build connection parameters from environment variables."""
    return {
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }


def wait_for_database(
    db_names: Iterable[str] | None = None,
    timeout: float = 60.0,
    interval: float = 2.0,
) -> bool:
    """Poll the database until a connection succeeds or timeout expires."""
    params = _connection_params()
    primary = os.getenv("DB_NAME", "notas")
    names = list(dict.fromkeys(db_names or (primary, "postgres")))

    deadline = time.time() + timeout
    while time.time() < deadline:
        for name in names:
            try:
                conn = psycopg2.connect(dbname=name, connect_timeout=int(max(interval, 1)), **params)
                conn.close()
                return True
            except OperationalError:
                continue
        time.sleep(interval)
    return False


def main() -> int:
    timeout = float(os.getenv("DB_WAIT_TIMEOUT", "60"))
    interval = float(os.getenv("DB_WAIT_INTERVAL", "2"))
    success = wait_for_database(timeout=timeout, interval=interval)
    if success:
        print("PostgreSQL disponível.")
        return 0
    print("PostgreSQL indisponível após aguardar.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
