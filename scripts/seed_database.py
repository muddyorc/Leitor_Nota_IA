#!/usr/bin/env python3
"""Popula o banco PostgreSQL com dados sintéticos para testes e RAG."""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from faker import Faker  # noqa: E402

from config.settings import REGRAS_DE_CLASSIFICACAO  # noqa: E402
from database.connection import Base, SessionLocal, engine  # noqa: E402
from database.models import (  # noqa: E402
    Classificacao,
    MovimentoContas,
    ParcelasContas,
    Pessoas,
)

DESPESA_CLASSIFICACOES = list(REGRAS_DE_CLASSIFICACAO.keys()) + ["LOGÍSTICA AGRÍCOLA"]

RECEITA_CLASSIFICACOES = [
    "Venda de Grãos",
    "Venda de Gado",
    "Venda de Leite",
    "Venda de Café",
    "Serviços de Pulverização",
    "Arrendamento de Terras",
    "Exportação de Soja",
    "Venda de Silagem",
    "Programas Governamentais",
    "Feiras e Exposições",
]

CLASSIFICACAO_PRESETS = {
    "DESPESA": DESPESA_CLASSIFICACOES,
    "RECEITA": RECEITA_CLASSIFICACOES,
}

FORNECEDOR_SUFFIXES = [
    "Agroinsumos",
    "Agropecuária",
    "Cooperativa",
    "Comercial Agrícola",
    "Distribuidora Rural",
    "Serviços Agrícolas",
]

CLIENTE_SUFFIXES = [
    "Fazenda",
    "Sítio",
    "Agro",
    "Produtora Rural",
    "Agroindustrial",
]

FATURADO_SUFFIXES = [
    "Produtor",
    "Gestão Rural",
    "Holding Agro",
]

AGRO_OPERACOES = [
    "Aplicação de calcário",
    "Plantio de soja",
    "Plantio de milho",
    "Colheita mecanizada",
    "Manutenção de pivô",
    "Aquisição de maquinário",
    "Adubação de cobertura",
    "Manejo de irrigação",
    "Contratação de frete agrícola",
    "Aquisição de defensivos",
]

AGRO_ITENS = [
    "sementes certificadas",
    "fertilizantes foliares",
    "defensivos biológicos",
    "rapadeiras",
    "pneus agrícolas",
    "óleo diesel S10",
    "consultoria de manejo",
    "equipamentos de irrigação",
    "serviço de pulverização",
    "kits de monitoramento",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera registros fake de pessoas, classificações e movimentos."
    )
    parser.add_argument("--fornecedores", type=int, default=20, help="Quantidade de fornecedores a criar")
    parser.add_argument("--clientes", type=int, default=20, help="Quantidade de clientes a criar")
    parser.add_argument("--faturados", type=int, default=10, help="Quantidade de faturados a criar")
    parser.add_argument("--classificacoes", type=int, default=10, help="Quantidade de classificações por tipo")
    parser.add_argument("--movimentos", type=int, default=200, help="Quantidade de movimentos a gerar")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade dos dados")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignora checagens e insere dados mesmo se já houver registros",
    )
    return parser.parse_args()


def quantize(valor: float | Decimal) -> Decimal:
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seed_pessoas(session, faker: Faker, fornecedores: int, clientes: int, faturados: int) -> dict[str, list[Pessoas]]:
    buckets = {"FORNECEDOR": [], "CLIENTE": [], "FATURADO": []}
    specs = [
        ("FORNECEDOR", fornecedores),
        ("CLIENTE", clientes),
        ("FATURADO", faturados),
    ]

    for tipo, total in specs:
        for _ in range(total):
            if tipo == "FATURADO":
                razao = f"{faker.last_name()} {random.choice(FATURADO_SUFFIXES)}"
                fantasia = f"{faker.first_name()} Rural"
                documento = faker.cpf()
            elif tipo == "CLIENTE":
                razao = f"{faker.last_name()} {random.choice(CLIENTE_SUFFIXES)}"
                fantasia = f"{faker.first_name()} {random.choice(['Agro', 'Fazenda', 'Produtor'])}"
                documento = faker.cnpj()
            else:
                razao = f"{faker.last_name()} {random.choice(FORNECEDOR_SUFFIXES)}"
                fantasia = f"Grupo {faker.city()} Agro"
                documento = faker.cnpj()

            pessoa = Pessoas(
                tipo=tipo,
                razaosocial=razao,
                fantasia=fantasia,
                documento=documento,
                status="ATIVO",
            )
            session.add(pessoa)
            buckets[tipo].append(pessoa)

    session.flush()
    return buckets


def seed_classificacoes(session, por_tipo: int) -> list[Classificacao]:
    registros: list[Classificacao] = []
    for tipo, descricoes in CLASSIFICACAO_PRESETS.items():
        pool = descricoes[:]
        random.shuffle(pool)
        selecionadas = pool[:por_tipo]
        for descricao in selecionadas:
            existente = (
                session.query(Classificacao)
                .filter(Classificacao.descricao == descricao, Classificacao.tipo == tipo)
                .first()
            )
            if existente:
                registros.append(existente)
                continue
            classificacao = Classificacao(tipo=tipo, descricao=descricao, status="ATIVO")
            session.add(classificacao)
            registros.append(classificacao)
    session.flush()
    return registros


def escolher_classificacoes(movimento_tipo: str, classificacoes: list[Classificacao]) -> list[Classificacao]:
    alvo = "DESPESA" if movimento_tipo == "PAGAR" else "RECEITA"
    candidatas = [c for c in classificacoes if (c.tipo or "").upper() == alvo]
    if not candidatas:
        candidatas = classificacoes
    quantidade = random.randint(1, min(3, len(candidatas)))
    return random.sample(candidatas, quantidade)


def distribuir_parcelas(valor_total: Decimal, data_base: date) -> list[ParcelasContas]:
    parcelas = []
    total_parcelas = random.randint(1, 4)
    valor_base = quantize(valor_total / total_parcelas)
    acumulado = Decimal("0.00")

    for indice in range(total_parcelas):
        if indice == total_parcelas - 1:
            valor = quantize(valor_total - acumulado)
        else:
            valor = valor_base
            acumulado += valor

        vencimento = data_base + timedelta(days=30 * (indice + 1))
        status = random.choice(["ABERTA", "LIQUIDADA", "PARCIAL"])
        if status == "LIQUIDADA":
            valor_pago = valor
            valor_saldo = Decimal("0.00")
        elif status == "PARCIAL":
            valor_pago = quantize(valor * Decimal("0.5"))
            valor_saldo = quantize(valor - valor_pago)
        else:
            valor_pago = Decimal("0.00")
            valor_saldo = valor

        parcelas.append(
            ParcelasContas(
                identificacao=f"PARC-{indice + 1:02d}/{total_parcelas:02d}",
                data_vencimento=vencimento,
                valor_parcela=valor,
                valor_pago=valor_pago,
                valor_saldo=valor_saldo,
                status_parcela=status,
            )
        )

    return parcelas


def seed_movimentos(
    session,
    faker: Faker,
    buckets: dict[str, list[Pessoas]],
    classificacoes: list[Classificacao],
    quantidade: int,
) -> None:
    for _ in range(quantidade):
        movimento_tipo = random.choice(["PAGAR", "RECEBER"])
        data_emissao = faker.date_between(start_date="-365d", end_date="today")
        valor_total = quantize(random.uniform(500, 20000))

        if movimento_tipo == "PAGAR" and buckets["FORNECEDOR"]:
            fornecedor = random.choice(buckets["FORNECEDOR"])
        else:
            fornecedor = random.choice(buckets["CLIENTE"] or buckets["FORNECEDOR"])

        faturado = random.choice(
            buckets["FATURADO"] or buckets["CLIENTE"] or buckets["FORNECEDOR"]
        )

        movimento = MovimentoContas(
            tipo=movimento_tipo,
            numero_nota_fiscal=str(faker.unique.random_number(digits=10)),
            data_emissao=data_emissao,
            descricao=f"{random.choice(AGRO_OPERACOES)} - {random.choice(AGRO_ITENS)}",
            status="ATIVO",
            valor_total=valor_total,
            fornecedor=fornecedor,
            faturado=faturado,
        )

        for classificacao in escolher_classificacoes(movimento_tipo, classificacoes):
            movimento.classificacoes.append(classificacao)

        for parcela in distribuir_parcelas(valor_total, data_emissao):
            movimento.parcelas.append(parcela)

        session.add(movimento)


def main() -> int:
    args = parse_args()
    faker = Faker("pt_BR")
    if args.seed is not None:
        random.seed(args.seed)
        faker.seed_instance(args.seed)

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    try:
        if not args.force:
            existentes = session.query(MovimentoContas).count()
            if existentes:
                print(
                    "Já existem movimentações cadastradas. Utilize --force para complementar os dados."
                )
                return 0

        pessoas = seed_pessoas(session, faker, args.fornecedores, args.clientes, args.faturados)
        classificacoes = seed_classificacoes(session, args.classificacoes)
        seed_movimentos(session, faker, pessoas, classificacoes, args.movimentos)

        session.commit()
        total_pessoas = sum(len(lista) for lista in pessoas.values())
        print(
            f"Seed concluído com sucesso: {total_pessoas} pessoas, "
            f"{len(classificacoes)} classificações e {args.movimentos} movimentos."
        )
        return 0
    except Exception as exc:  # pragma: no cover - log utilitário
        session.rollback()
        print(f"Erro ao executar seed: {exc}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
