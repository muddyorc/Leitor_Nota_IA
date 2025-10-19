"""Agente responsável por persistir os dados extraídos pelo LLM no banco."""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Classificacao, MovimentoContas, ParcelasContas, Pessoas


class PersistenciaAgent:
    """Camada de orquestração das operações de persistência via SQLAlchemy."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session_scope(self) -> Iterable[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_or_create_pessoa(
        self,
        dados_pessoa: Dict[str, Any],
        *,
        tipo_padrao: Optional[str] = None,
        session: Optional[Session] = None,
        criar_se_ausente: bool = True,
    ) -> Optional[int]:
        """Busca uma pessoa pelo documento ou cria um novo registro.

        Retorna o ID existente/criado ou ``None`` quando não há dados suficientes.
        """

        if not dados_pessoa:
            return None

        manage_session = session is None
        session = session or self._session_factory()

        try:
            documento = self._sanitize_documento(
                dados_pessoa.get("documento")
                or dados_pessoa.get("cnpj")
                or dados_pessoa.get("cpf")
            )
            if not documento:
                return None

            stmt = select(Pessoas).where(Pessoas.documento == documento)
            pessoa = session.execute(stmt).scalar_one_or_none()
            if pessoa:
                return pessoa.id
            if not criar_se_ausente:
                return None

            pessoa = Pessoas(
                tipo=tipo_padrao or self._inferir_tipo_pessoa(dados_pessoa),
                razaosocial=dados_pessoa.get("razaoSocial") or dados_pessoa.get("nomeCompleto"),
                fantasia=dados_pessoa.get("fantasia"),
                documento=documento,
                status=dados_pessoa.get("status") or "ATIVO",
            )
            session.add(pessoa)
            session.flush()
            if manage_session:
                session.commit()
            return pessoa.id
        finally:
            if manage_session:
                session.close()

    def get_or_create_classificacao(
        self,
        dados_classificacao: Any,
        *,
        session: Optional[Session] = None,
        criar_se_ausente: bool = True,
    ) -> Optional[int]:
        """Garante a existência da classificação e retorna seu ID."""

        descricao = self._extrair_descricao_classificacao(dados_classificacao)
        if not descricao:
            return None

        manage_session = session is None
        session = session or self._session_factory()

        try:
            stmt = select(Classificacao).where(func.lower(Classificacao.descricao) == descricao.lower())
            classificacao = session.execute(stmt).scalar_one_or_none()
            if classificacao:
                return classificacao.id
            if not criar_se_ausente:
                return None

            classificacao = Classificacao(
                tipo=self._extrair_tipo_classificacao(dados_classificacao),
                descricao=descricao,
                status="ATIVO",
            )
            session.add(classificacao)
            session.flush()
            if manage_session:
                session.commit()
            return classificacao.id
        finally:
            if manage_session:
                session.close()

    def lancar_conta_pagar(self, dados_json: Dict[str, Any]) -> Dict[str, Any]:
        """Cria (ou atualiza) o movimento, parcelas e vínculos de classificação."""

        if not dados_json:
            raise ValueError("dados_json vazio")

        with self._session_scope() as session:
            fornecedor_id = self.get_or_create_pessoa(
                dados_json.get("fornecedor", {}),
                tipo_padrao="FORNECEDOR",
                session=session,
            )
            faturado_id = self.get_or_create_pessoa(
                dados_json.get("faturado", {}),
                tipo_padrao="FATURADO",
                session=session,
            )

            movimento = self._upsert_movimento(
                session,
                dados_json,
                fornecedor_id,
                faturado_id,
            )

            self._sincronizar_classificacoes(
                session,
                movimento,
                dados_json.get("classificacaoDespesa") or ["Outros"],
            )
            self._sincronizar_parcelas(
                movimento,
                dados_json.get("parcelas") or [],
            )

            session.flush()
            session.refresh(movimento)

            return {
                "movimento_id": movimento.id,
                "parcelas_ids": [parcela.id for parcela in movimento.parcelas],
                "classificacao_ids": [cls.id for cls in movimento.classificacoes],
                "fornecedor_id": fornecedor_id,
                "faturado_id": faturado_id,
            }

    def verificar_entidades(self, dados_json: Dict[str, Any]) -> Dict[str, Any]:
        """Retorna o status de existência das entidades envolvidas sem realizar inserções."""

        session = self._session_factory()
        try:
            fornecedor_info = self._verificar_pessoa(
                session,
                dados_json.get("fornecedor", {}),
                tipo_padrao="FORNECEDOR",
            )
            faturado_info = self._verificar_pessoa(
                session,
                dados_json.get("faturado", {}),
                tipo_padrao="FATURADO",
            )

            classificacoes_info = []
            for item in dados_json.get("classificacaoDespesa") or []:
                descricao = self._extrair_descricao_classificacao(item)
                if not descricao:
                    continue
                stmt = select(Classificacao).where(func.lower(Classificacao.descricao) == descricao.lower())
                classificacao = session.execute(stmt).scalar_one_or_none()
                classificacoes_info.append(
                    {
                        "descricao": descricao,
                        "status": "EXISTE" if classificacao else "NÃO EXISTE",
                        "id": classificacao.id if classificacao else None,
                    }
                )

            return {
                "fornecedor": fornecedor_info,
                "faturado": faturado_info,
                "classificacoes": classificacoes_info,
            }
        finally:
            session.close()

    def _upsert_movimento(
        self,
        session: Session,
        dados_json: Dict[str, Any],
        fornecedor_id: Optional[int],
        faturado_id: Optional[int],
    ) -> MovimentoContas:
        numero_nota = dados_json.get("numeroNotaFiscal")
        stmt = select(MovimentoContas).where(MovimentoContas.numero_nota_fiscal == numero_nota)
        if fornecedor_id:
            stmt = stmt.where(MovimentoContas.fornecedor_id == fornecedor_id)

        movimento = session.execute(stmt).scalar_one_or_none()
        if movimento is None:
            movimento = MovimentoContas()
            session.add(movimento)

        movimento.tipo = dados_json.get("tipo") or "Despesa"
        movimento.numero_nota_fiscal = numero_nota
        movimento.data_emissao = self._parse_date(
            dados_json.get("dataEmissao") or dados_json.get("data_emissao")
        )
        movimento.descricao = dados_json.get("descricao") or dados_json.get("observacoes")
        movimento.status = dados_json.get("status") or "ABERTO"
        movimento.valor_total = self._to_decimal(
            dados_json.get("valorTotal") or dados_json.get("valor_total")
        )
        movimento.fornecedor_id = fornecedor_id
        movimento.faturado_id = faturado_id

        return movimento

    def _sincronizar_classificacoes(
        self,
        session: Session,
        movimento: MovimentoContas,
        classificacoes_payload: Iterable[Any],
    ) -> None:
        movimento.classificacoes.clear()
        for item in classificacoes_payload:
            class_id = self.get_or_create_classificacao(item, session=session)
            if not class_id:
                continue
            classificacao = session.get(Classificacao, class_id)
            if classificacao and classificacao not in movimento.classificacoes:
                movimento.classificacoes.append(classificacao)

    def _sincronizar_parcelas(
        self,
        movimento: MovimentoContas,
        parcelas_payload: Iterable[Dict[str, Any]],
    ) -> None:
        movimento.parcelas.clear()
        for indice, parcela_raw in enumerate(parcelas_payload, start=1):
            parcela = ParcelasContas(
                identificacao=self._coalesce_str(
                    parcela_raw.get("identificacao"),
                    parcela_raw.get("Identificacao"),
                    f"Parcela {indice}",
                ),
                data_vencimento=self._parse_date(
                    parcela_raw.get("dataVencimento")
                    or parcela_raw.get("data_vencimento")
                ),
                valor_parcela=self._to_decimal(
                    parcela_raw.get("valorParcela")
                    or parcela_raw.get("valor_parcela")
                ),
                valor_pago=self._to_decimal(
                    parcela_raw.get("valorPago")
                    or parcela_raw.get("valor_pago")
                ),
                valor_saldo=self._to_decimal(
                    parcela_raw.get("valorSaldo")
                    or parcela_raw.get("valor_saldo")
                ),
                status_parcela=self._coalesce_str(
                    parcela_raw.get("statusParcela"),
                    parcela_raw.get("status_parcela"),
                    "PENDENTE",
                ),
            )
            movimento.parcelas.append(parcela)

    @staticmethod
    def _sanitize_documento(documento: Optional[str]) -> Optional[str]:
        if documento is None:
            return None
        somente_digitos = re.sub(r"\D", "", documento)
        return somente_digitos or None

    @staticmethod
    def _inferir_tipo_pessoa(dados_pessoa: Dict[str, Any]) -> Optional[str]:
        if dados_pessoa.get("cnpj"):
            return "FORNECEDOR"
        if dados_pessoa.get("cpf"):
            return "FATURADO"
        return None

    def _verificar_pessoa(
        self,
        session: Session,
        dados_pessoa: Dict[str, Any],
        *,
        tipo_padrao: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not dados_pessoa:
            return {
                "status": "NÃO INFORMADO",
                "id": None,
                "documento": None,
                "tipo": tipo_padrao,
            }

        documento = self._sanitize_documento(
            dados_pessoa.get("documento")
            or dados_pessoa.get("cnpj")
            or dados_pessoa.get("cpf")
        )
        if not documento:
            return {
                "status": "NÃO INFORMADO",
                "id": None,
                "documento": None,
                "tipo": tipo_padrao,
            }

        stmt = select(Pessoas).where(Pessoas.documento == documento)
        pessoa = session.execute(stmt).scalar_one_or_none()

        return {
            "status": "EXISTE" if pessoa else "NÃO EXISTE",
            "id": pessoa.id if pessoa else None,
            "documento": documento,
            "tipo": tipo_padrao or self._inferir_tipo_pessoa(dados_pessoa),
            "nome": dados_pessoa.get("razaoSocial")
            or dados_pessoa.get("nomeCompleto")
            or dados_pessoa.get("fantasia"),
        }

    @staticmethod
    def _extrair_descricao_classificacao(dados_classificacao: Any) -> Optional[str]:
        if isinstance(dados_classificacao, str):
            return dados_classificacao.strip() or None
        if isinstance(dados_classificacao, dict):
            return (
                dados_classificacao.get("descricao")
                or dados_classificacao.get("nome")
                or dados_classificacao.get("label")
            )
        return None

    @staticmethod
    def _extrair_tipo_classificacao(dados_classificacao: Any) -> Optional[str]:
        if isinstance(dados_classificacao, dict):
            return dados_classificacao.get("tipo")
        return "DESPESA"

    @staticmethod
    def _parse_date(valor: Any) -> Optional[date]:
        if valor in (None, ""):
            return None
        if isinstance(valor, date):
            return valor
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, str):
            valor = valor.strip()
            for formato in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(valor, formato).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _to_decimal(valor: Any) -> Optional[Decimal]:
        if valor in (None, ""):
            return None
        if isinstance(valor, Decimal):
            return valor
        if isinstance(valor, (int, float)):
            return Decimal(str(valor))
        if isinstance(valor, str):
            normalizado = valor.strip()
            normalizado = normalizado.replace("R$", "")
            normalizado = normalizado.replace(" ", "")
            normalizado = normalizado.replace(".", "")
            normalizado = normalizado.replace(",", ".")
            try:
                return Decimal(normalizado)
            except (InvalidOperation, ArithmeticError):
                return None
        return None

    @staticmethod
    def _coalesce_str(*valores: Optional[str]) -> Optional[str]:
        for valor in valores:
            if isinstance(valor, str) and valor.strip():
                return valor.strip()
        return None
