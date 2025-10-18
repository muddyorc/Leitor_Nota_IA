"""ORM models that map the DER diagram to SQLAlchemy classes."""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .connection import Base


# Association table between MovimentoContas and Classificacao (many-to-many)
movimento_classificacao_association = Table(
    "MovimentoContas_has_Classificacao",
    Base.metadata,
    Column(
        "MovimentoContas_idMovimentoContas",
        ForeignKey("movimento_contas.idMovimentoContas"),
        primary_key=True,
    ),
    Column(
        "Classificacao_idClassificacao",
        ForeignKey("classificacao.idClassificacao"),
        primary_key=True,
    ),
)


class Pessoas(Base):
    """Informações cadastrais de pessoas físicas ou jurídicas."""

    __tablename__ = "pessoas"

    id: Mapped[int] = mapped_column("idPessoas", Integer, primary_key=True, autoincrement=True, quote=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(45))
    razaosocial: Mapped[Optional[str]] = mapped_column(String(150))
    fantasia: Mapped[Optional[str]] = mapped_column(String(150))
    documento: Mapped[Optional[str]] = mapped_column(String(45))
    status: Mapped[Optional[str]] = mapped_column(String(45))

    movimentos_como_fornecedor: Mapped[List["MovimentoContas"]] = relationship(
        "MovimentoContas",
        back_populates="fornecedor",
        foreign_keys="MovimentoContas.fornecedor_id",
    )
    movimentos_como_faturado: Mapped[List["MovimentoContas"]] = relationship(
        "MovimentoContas",
        back_populates="faturado",
        foreign_keys="MovimentoContas.faturado_id",
    )


class Classificacao(Base):
    """Categorias de despesas segundo o modelo financeiro."""

    __tablename__ = "classificacao"

    id: Mapped[int] = mapped_column("idClassificacao", Integer, primary_key=True, autoincrement=True, quote=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(45))
    descricao: Mapped[Optional[str]] = mapped_column(String(150))
    status: Mapped[Optional[str]] = mapped_column(String(45))

    movimentos: Mapped[List["MovimentoContas"]] = relationship(
        "MovimentoContas",
        secondary=movimento_classificacao_association,
        back_populates="classificacoes",
    )


class MovimentoContas(Base):
    """Registro principal de cada nota fiscal processada."""

    __tablename__ = "movimento_contas"

    id: Mapped[int] = mapped_column("idMovimentoContas", Integer, primary_key=True, autoincrement=True, quote=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(45))
    numero_nota_fiscal: Mapped[Optional[str]] = mapped_column("numeronotafiscal", String(45))
    data_emissao: Mapped[Optional[Date]] = mapped_column("dataemissao", Date)
    descricao: Mapped[Optional[str]] = mapped_column(String(300))
    status: Mapped[Optional[str]] = mapped_column(String(45))
    valor_total: Mapped[Optional[Decimal]] = mapped_column("valortotal", Numeric(14, 2))

    fornecedor_id: Mapped[Optional[int]] = mapped_column(
        "Pessoas_idFornecedorCliente",
        Integer,
        ForeignKey("pessoas.idPessoas"),
        quote=True,
    )
    faturado_id: Mapped[Optional[int]] = mapped_column(
        "Pessoas_idFaturado",
        Integer,
        ForeignKey("pessoas.idPessoas"),
        quote=True,
    )

    fornecedor: Mapped[Optional[Pessoas]] = relationship(
        "Pessoas",
        foreign_keys=[fornecedor_id],
        back_populates="movimentos_como_fornecedor",
    )
    faturado: Mapped[Optional[Pessoas]] = relationship(
        "Pessoas",
        foreign_keys=[faturado_id],
        back_populates="movimentos_como_faturado",
    )

    parcelas: Mapped[List["ParcelasContas"]] = relationship(
        "ParcelasContas",
        back_populates="movimento",
        cascade="all, delete-orphan",
    )

    classificacoes: Mapped[List[Classificacao]] = relationship(
        "Classificacao",
        secondary=movimento_classificacao_association,
        back_populates="movimentos",
    )


class ParcelasContas(Base):
    """Parcelas geradas para pagamentos futuros vinculados ao movimento."""

    __tablename__ = "parcelas_contas"

    id: Mapped[int] = mapped_column("idParcelasContas", Integer, primary_key=True, autoincrement=True, quote=True)
    identificacao: Mapped[Optional[str]] = mapped_column("Identiticacao", String(45), quote=True)
    data_vencimento: Mapped[Optional[Date]] = mapped_column("datavencimento", Date)
    valor_parcela: Mapped[Optional[Decimal]] = mapped_column("valorparcela", Numeric(14, 2))
    valor_pago: Mapped[Optional[Decimal]] = mapped_column("valorpago", Numeric(14, 2))
    valor_saldo: Mapped[Optional[Decimal]] = mapped_column("valorsaldo", Numeric(14, 2))
    status_parcela: Mapped[Optional[str]] = mapped_column("statusparcela", String(45))
    movimento_id: Mapped[int] = mapped_column(
        "MovimentoContas_idMovimentoContas",
        Integer,
        ForeignKey("movimento_contas.idMovimentoContas", ondelete="CASCADE"),
        nullable=False,
        quote=True,
    )

    movimento: Mapped[MovimentoContas] = relationship(
        "MovimentoContas",
        back_populates="parcelas",
    )
