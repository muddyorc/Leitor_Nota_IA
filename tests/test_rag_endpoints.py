"""Testes dos endpoints relacionados à consulta RAG."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app  # noqa: E402


@pytest.fixture()
def rag_client(monkeypatch):
    """Configura o `consulta_agent` com stubs previsíveis para os testes."""

    fake_agent = SimpleNamespace(
        executar_consulta_simples=lambda pergunta: f"simples::{pergunta}",
        executar_consulta_semantica=lambda pergunta: f"semantico::{pergunta}",
    )
    monkeypatch.setattr("app.consulta_agent", fake_agent)
    client = app.test_client()
    yield client, fake_agent


def test_consulta_page_renderiza_template(rag_client):
    client, _ = rag_client

    response = client.get("/consulta")

    assert response.status_code == 200
    assert b"Consulta Anal\xc3\xadtica (RAG)" in response.data


def test_consultar_rag_modo_simples(rag_client):
    client, _ = rag_client

    response = client.post(
        "/consultar_rag",
        json={"pergunta": "Qual o total?", "modo": "simples"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"resposta": "simples::Qual o total?"}


def test_consultar_rag_modo_semantico(rag_client):
    client, fake_agent = rag_client

    response = client.post(
        "/consultar_rag",
        json={"pergunta": "E as ultimas notas?", "modo": "semantico"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"resposta": "semantico::E as ultimas notas?"}


def test_consultar_rag_sem_pergunta_retorna_400(rag_client):
    client, _ = rag_client

    response = client.post(
        "/consultar_rag",
        json={"modo": "simples"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Pergunta inválida"


def test_consultar_rag_json_invalido_retorna_400(rag_client):
    client, _ = rag_client

    response = client.post(
        "/consultar_rag",
        data="{invalid",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "JSON inválido"


def test_consultar_rag_quando_agente_erro_retorna_500(rag_client, monkeypatch):
    client, fake_agent = rag_client

    def _raise(_):
        raise RuntimeError("falha controlada")

    monkeypatch.setattr(fake_agent, "executar_consulta_simples", _raise)

    response = client.post(
        "/consultar_rag",
        json={"pergunta": "Oi", "modo": "simples"},
    )

    body = response.get_json()
    assert response.status_code == 500
    assert body["error"] == "Falha na consulta RAG"
    assert "falha controlada" in body["detalhes"]
