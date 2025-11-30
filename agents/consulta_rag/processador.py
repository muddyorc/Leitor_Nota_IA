# agents/consulta_rag/processador.py
from __future__ import annotations
from typing import Callable, Optional

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased
from database.connection import SessionLocal
from config.settings import GOOGLE_API_KEY  # caso precise, mas usamos ia_service para gerar texto
from agents.AgentePersistencia.processador import PersistenciaAgent
import os

from database.models import Classificacao, MovimentoContas, ParcelasContas, Pessoas

# --- lazy imports for semantic retrieval (heavy libs, loaded only when needed) ---
CHROMA_AVAILABLE = True  # assume available unless proven otherwise

# Use your existing ia wrapper to call Gemini
from agents.AgenteExtracao.ia_service import responder_pergunta_com_llm  # Gemini wrapper adaptado para respostas textuais

_STOP_WORDS = {
    "qual",
    "quais",
    "que",
    "quanto",
    "quantos",
    "quando",
    "como",
    "para",
    "com",
    "dos",
    "das",
    "do",
    "da",
    "de",
    "nos",
    "nas",
    "uma",
    "um",
    "das",
    "dos",
    "as",
    "os",
    "notas",
    "nota",
    "valor",
    "foi",
    "foram",
    "recebidos",
    "recebido",
}
# If you have a dedicated function for prompting Gemini, prefer that. Here we reuse ia_service as it exists. :contentReference[oaicite:4]{index=4}

class ConsultaRagAgent:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        chroma_dir: str | None = None,
        llm_callable: Optional[Callable[[str], str]] = None,
        chroma_client=None,
        embed_model=None,
        enable_chroma: bool | None = None,
        api_key_resolver: Callable[[], str | None] | None = None,
    ):
        self._session_factory = session_factory
        self.persist_agent = PersistenciaAgent(session_factory)
        self.chroma_dir = chroma_dir or os.getenv("CHROMA_DIR", "./_chromadb")
        self._chroma_client = chroma_client
        self._embed_model = embed_model
        self._llm_callable = llm_callable or responder_pergunta_com_llm
        self._api_key_resolver = api_key_resolver

        if enable_chroma is None:
            enable_chroma = CHROMA_AVAILABLE
        self._enable_chroma = bool(enable_chroma and CHROMA_AVAILABLE)

        self._intent_templates = [
            {
                "name": "contas_pagar_recente",
                "keywords_all": ["conta", "pagar"],
                "keywords_any": ["acima", "maior", "superior"],
                "handler": self._handle_contas_pagar_recente,
            },
            {
                "name": "fornecedores_freq_mes",
                "keywords_all": ["fornecedor"],
                "keywords_any": ["lançamento", "lancamento", "entrada"],
                "requires_terms": ["mês", "mes"],
                "handler": self._handle_fornecedores_freq_mes,
            },
            {
                "name": "faturados_parcelas_abertas",
                "keywords_all": ["faturado", "parcela"],
                "keywords_any": ["aberta", "aberto", "pendente"],
                "handler": self._handle_faturados_parcelas_abertas,
            },
            {
                "name": "classificacoes_trimestre",
                "keywords_all": ["classifica"],
                "keywords_any": ["trimestre", "trimestral"],
                "handler": self._handle_classificacoes_trimestre,
            },
            {
                "name": "notas_receber_mes",
                "keywords_all": ["receber", "nota"],
                "handler": self._handle_notas_receber_mes,
            },
        ]

        self._semantic_templates = [
            {
                "name": "manutencao_maquinario",
                "keywords_all": ["manuten", "maquin"],
                "handler": self._sem_manutencao_maquinario,
            },
            {
                "name": "evolucao_insumos",
                "keywords_all": ["insumo"],
                "keywords_any": ["evol", "compar"],
                "handler": self._sem_evolucao_insumos,
            },
            {
                "name": "clientes_receita",
                "keywords_all": ["cliente", "receita"],
                "handler": self._sem_clientes_receita_90,
            },
            {
                "name": "fornecedores_atraso",
                "keywords_all": ["fornecedor", "atras"],
                "handler": self._sem_fornecedores_atraso,
            },
            {
                "name": "custos_logisticos",
                "keywords_all": ["logist"],
                "handler": self._sem_custos_logisticos_semestre,
            },
        ]

        if self._enable_chroma and (self._chroma_client is None or self._embed_model is None):
            try:
                self._init_chroma()
            except Exception as exc:  # noqa: BLE001 - queremos sobreviver em ambiente sem Chroma
                print(f"ChromaDB desabilitado: {exc}")
                self._enable_chroma = False
                self._chroma_client = None
                self._embed_model = None

    @staticmethod
    def _format_currency(value) -> str:
        try:
            numeric = float(value or 0)
        except (TypeError, ValueError):
            numeric = 0.0
        formatted = f"R$ {numeric:,.2f}"
        return formatted.replace(",", "_").replace(".", ",").replace("_", ".")

    @staticmethod
    def _should_include_summary(pergunta: str | None) -> bool:
        if not pergunta:
            return False
        termos_chave = ("custo", "gasto", "despesa", "recorr", "combust", "manut", "significativo")
        pergunta_lower = pergunta.lower()
        return any(chave in pergunta_lower for chave in termos_chave)

    @staticmethod
    def _extract_numeric_candidates(texto: str) -> list[float]:
        if not texto:
            return []
        matches = re.findall(r"\d[\d\.,]*", texto.replace("R$", ""))
        valores = []
        for raw in matches:
            normalizado = raw.replace(".", "").replace(",", ".")
            try:
                valores.append(float(normalizado))
            except ValueError:
                continue
        return valores

    @staticmethod
    def _extract_currency_threshold(texto: str, default: float = 0.0) -> float:
        valores = ConsultaRagAgent._extract_numeric_candidates(texto)
        monetarios = [valor for valor in valores if valor > 31]
        if monetarios:
            return max(monetarios)
        return valores[0] if valores else default

    @staticmethod
    def _extract_day_window(texto: str, default: int = 30) -> int:
        if not texto:
            return default
        match = re.search(r"(\d+)[\s-]*(dia|dias)", texto, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return default
        if "trinta" in texto.lower():
            return 30
        return default

    @staticmethod
    def _extract_having_threshold(texto: str, default: int = 5) -> int:
        valores = ConsultaRagAgent._extract_numeric_candidates(texto)
        for valor in valores:
            inteiro = int(valor)
            if inteiro > 0:
                return inteiro
        return default

    @staticmethod
    def _extract_month_year(texto: str) -> tuple[int | None, int | None]:
        if not texto:
            return None, None
        meses = {
            "janeiro": 1,
            "fevereiro": 2,
            "março": 3,
            "marco": 3,
            "abril": 4,
            "maio": 5,
            "junho": 6,
            "julho": 7,
            "agosto": 8,
            "setembro": 9,
            "outubro": 10,
            "novembro": 11,
            "dezembro": 12,
        }
        texto_lower = texto.lower()
        for nome, numero in meses.items():
            if nome in texto_lower:
                ano_match = re.search(r"20\d{2}", texto)
                ano = int(ano_match.group(0)) if ano_match else date.today().year
                return numero, ano
        return None, None

    @staticmethod
    def _start_of_current_month() -> date:
        hoje = date.today()
        return hoje.replace(day=1)

    @staticmethod
    def _start_of_current_quarter() -> date:
        hoje = date.today()
        quarter = (hoje.month - 1) // 3 + 1
        first_month = 3 * (quarter - 1) + 1
        return date(hoje.year, first_month, 1)

    def _init_chroma(self):
        # initializes chroma client and embedder if available (lazy loading)
        if not self._enable_chroma:
            return

        try:
            # Lazy import: only load when actually needed
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            print(f"ChromaDB ou SentenceTransformer não disponíveis: {e}")
            self._enable_chroma = False
            return

        persist_path = Path(self.chroma_dir).resolve()
        persist_path.mkdir(parents=True, exist_ok=True)

        if self._embed_model is None:
            self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")

        persistent_client_cls = getattr(chromadb, "PersistentClient", None)
        if persistent_client_cls is not None:
            self._chroma_client = persistent_client_cls(path=str(persist_path))
        else:
            from chromadb.config import Settings as ChromaSettings  # type: ignore[import]

            self._chroma_client = chromadb.Client(
                ChromaSettings(chroma_db_impl="duckdb+parquet", persist_directory=str(persist_path))
            )

    def _get_or_create_collection(self):
        if not self._enable_chroma or self._chroma_client is None:
            return None
        try:
            return self._chroma_client.get_collection("movimentos")
        except Exception:
            try:
                return self._chroma_client.create_collection("movimentos")
            except Exception:
                return None

    def _build_summary_context(self, session: Session, limite: int = 5) -> str:
        resumo_partes: list[str] = []

        classificacao_totais = (
            session.query(Classificacao.descricao, func.sum(MovimentoContas.valor_total).label("total"))
            .join(Classificacao.movimentos)
            .group_by(Classificacao.descricao)
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .limit(limite)
            .all()
        )
        if classificacao_totais:
            linhas = [
                f"- {descricao or 'Sem classificacao'}: {self._format_currency(total)}"
                for descricao, total in classificacao_totais
                if total is not None
            ]
            if linhas:
                resumo_partes.append("Classificacoes com maiores gastos:\n" + "\n".join(linhas))

        fornecedor_totais = (
            session.query(Pessoas.razaosocial, func.sum(MovimentoContas.valor_total).label("total"))
            .join(MovimentoContas, MovimentoContas.fornecedor_id == Pessoas.id)
            .group_by(Pessoas.razaosocial)
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .limit(limite)
            .all()
        )
        if fornecedor_totais:
            linhas = [
                f"- {nome or 'Fornecedor nao informado'}: {self._format_currency(total)}"
                for nome, total in fornecedor_totais
                if total is not None
            ]
            if linhas:
                resumo_partes.append("Fornecedores mais onerosos:\n" + "\n".join(linhas))

        recorrentes = (
            session.query(
                MovimentoContas.descricao,
                func.count(MovimentoContas.id).label("freq"),
                func.sum(MovimentoContas.valor_total).label("total"),
            )
            .group_by(MovimentoContas.descricao)
            .having(func.count(MovimentoContas.id) > 1)
            .order_by(func.count(MovimentoContas.id).desc(), func.sum(MovimentoContas.valor_total).desc())
            .limit(limite)
            .all()
        )
        if recorrentes:
            linhas = [
                f"- {descricao or 'Descricao nao informada'}: {freq} ocorrencias somando {self._format_currency(total)}"
                for descricao, freq, total in recorrentes
                if total is not None
            ]
            if linhas:
                resumo_partes.append("Gastos recorrentes detectados:\n" + "\n".join(linhas))

        return "\n\n".join(resumo_partes)

    # ---------------- RAG Simples ----------------
    def _retrieve_data_simples(self, pergunta: str, limit: int = 10) -> str:
        """Executa uma query SQL direta e retorna um contexto textual"""
        session: Session = self._session_factory()
        try:
            fornecedor_alias = aliased(Pessoas)
            faturado_alias = aliased(Pessoas)
            class_alias = aliased(Classificacao)

            base_stmt = (
                select(MovimentoContas)
                .outerjoin(fornecedor_alias, MovimentoContas.fornecedor)
                .outerjoin(faturado_alias, MovimentoContas.faturado)
                .outerjoin(class_alias, MovimentoContas.classificacoes)
            )

            tokens_raw = re.findall(r"\b\w{3,}\b", pergunta.lower()) if pergunta else []
            tokens = []
            for token in tokens_raw:
                if token in _STOP_WORDS or token in tokens:
                    continue
                tokens.append(token)
            filters = []
            for token in tokens[:5]:  # limita tokens relevantes para evitar filtros excessivos
                pattern = f"%{token}%"
                filters.extend(
                    [
                        MovimentoContas.descricao.ilike(pattern),
                        MovimentoContas.numero_nota_fiscal.ilike(pattern),
                        fornecedor_alias.razaosocial.ilike(pattern),
                        fornecedor_alias.fantasia.ilike(pattern),
                        faturado_alias.razaosocial.ilike(pattern),
                        faturado_alias.fantasia.ilike(pattern),
                        class_alias.descricao.ilike(pattern),
                    ]
                )

            stmt = base_stmt
            if filters:
                stmt = stmt.where(or_(*filters))

            stmt = stmt.order_by(MovimentoContas.data_emissao.desc()).limit(limit)
            rows = session.execute(stmt).scalars().unique().all()

            if not rows and filters:
                fallback_stmt = base_stmt.order_by(MovimentoContas.data_emissao.desc()).limit(limit)
                rows = session.execute(fallback_stmt).scalars().unique().all()

            resumo_texto = ""
            if self._should_include_summary(pergunta):
                resumo_texto = self._build_summary_context(session)

            partes = []
            for movimento in rows:
                fornecedor = None
                faturado = None
                if movimento.fornecedor:
                    fornecedor = movimento.fornecedor.razaosocial or movimento.fornecedor.fantasia
                if movimento.faturado:
                    faturado = movimento.faturado.razaosocial or movimento.faturado.fantasia

                classificacoes = [c.descricao for c in movimento.classificacoes or [] if c.descricao]
                classificacao_texto = ", ".join(classificacoes) if classificacoes else None

                partes.append(
                    "Movimento "
                    f"{movimento.id}: nota {movimento.numero_nota_fiscal}, "
                    f"data {movimento.data_emissao}, valor {movimento.valor_total}, descricao: {movimento.descricao}"
                    + (f", fornecedor: {fornecedor}" if fornecedor else "")
                    + (f", faturado: {faturado}" if faturado else "")
                    + (f", classificações: {classificacao_texto}" if classificacao_texto else "")
                )
            contexto = "\n".join(partes) or "Nenhum registro encontrado."
            if resumo_texto:
                if contexto and contexto != "Nenhum registro encontrado.":
                    contexto = f"{contexto}\n\nResumo financeiro:\n{resumo_texto}"
                else:
                    contexto = f"Resumo financeiro:\n{resumo_texto}"
            return contexto
        finally:
            session.close()

    def executar_consulta_simples(self, pergunta: str) -> str:
        resposta_direta = self._responder_pergunta_estruturada(pergunta)
        if resposta_direta:
            return resposta_direta
        contexto = self._retrieve_data_simples(pergunta)
        prompt = (
            f"Você é um analista financeiro. Com base **apenas** nos seguintes dados do sistema:\n\n"
            f"{contexto}\n\n"
            f"Responda a seguinte pergunta do usuário: {pergunta}\n\n"
            f"Se os dados não forem suficientes, informe que a resposta não pode ser encontrada."
        )
        # Reutiliza a função de consulta ao Gemini configurada para respostas textuais.
        api_key = self._resolve_api_key()
        resposta = self._llm_callable(prompt, api_key=api_key)
        return resposta or "Falha ao gerar resposta via LLM."

    def _responder_pergunta_estruturada(self, pergunta: str | None) -> str | None:
        if not pergunta:
            return None
        texto = pergunta.lower()
        session: Session = self._session_factory()
        try:
            for template in self._intent_templates:
                if not self._matches_intent(texto, template):
                    continue
                resposta = template["handler"](session, texto, pergunta)
                if resposta:
                    return resposta
        finally:
            session.close()
        return None

    @staticmethod
    def _matches_intent(pergunta_lower: str, template: dict) -> bool:
        for termo in template.get("keywords_all", []):
            if termo not in pergunta_lower:
                return False
        keywords_any = template.get("keywords_any")
        if keywords_any:
            if not any(termo in pergunta_lower for termo in keywords_any):
                return False
        required_terms = template.get("requires_terms")
        if required_terms:
            if not any(termo in pergunta_lower for termo in required_terms):
                return False
        predicate = template.get("predicate")
        if predicate and not predicate(pergunta_lower):
            return False
        return True

    # --- Handlers específicos ---
    def _handle_contas_pagar_recente(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        if "conta" not in pergunta_lower or "pagar" not in pergunta_lower:
            return None
        if "acima" not in pergunta_lower and "maior" not in pergunta_lower:
            return None
        dias = self._extract_day_window(pergunta_original, 30)
        minimo = self._extract_currency_threshold(pergunta_original, 10000.0)
        data_corte = date.today() - timedelta(days=dias)
        registros = (
            session.query(MovimentoContas)
            .filter(
                MovimentoContas.tipo == "PAGAR",
                MovimentoContas.valor_total >= Decimal(str(minimo)),
                MovimentoContas.data_emissao >= data_corte,
            )
            .order_by(MovimentoContas.data_emissao.desc())
            .limit(50)
            .all()
        )
        if not registros:
            return "Nenhuma conta a pagar encontrada dentro dos critérios solicitados."

        linhas = []
        for mov in registros:
            linhas.append(
                "- Nota {nota} em {data} | Valor {valor} | Fornecedor: {forn} | Faturado: {fat} | Descrição: {desc}".format(
                    nota=mov.numero_nota_fiscal or "N/A",
                    data=mov.data_emissao.strftime("%d/%m/%Y") if mov.data_emissao else "Sem data",
                    valor=self._format_currency(mov.valor_total),
                    forn=(mov.fornecedor.razaosocial if mov.fornecedor else "Não informado"),
                    fat=(mov.faturado.razaosocial if mov.faturado else "Não informado"),
                    desc=mov.descricao or "Sem descrição",
                )
            )
        return (
            f"Contas a pagar com valor a partir de {self._format_currency(minimo)} lançadas nos últimos {dias} dias:\n"
            + "\n".join(linhas)
        )

    def _handle_fornecedores_freq_mes(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        if "fornecedor" not in pergunta_lower:
            return None
        if "lançamento" not in pergunta_lower and "lancamento" not in pergunta_lower:
            return None
        if "mês" not in pergunta_lower and "mes" not in pergunta_lower:
            return None

        minimo = self._extract_having_threshold(pergunta_original, 5)
        inicio_mes = self._start_of_current_month()

        resultados = (
            session.query(
                Pessoas.razaosocial,
                func.count(MovimentoContas.id).label("total_lancamentos"),
                func.sum(MovimentoContas.valor_total).label("total_valor"),
            )
            .join(MovimentoContas, MovimentoContas.fornecedor_id == Pessoas.id)
            .filter(MovimentoContas.data_emissao >= inicio_mes)
            .group_by(Pessoas.id)
            .having(func.count(MovimentoContas.id) > minimo)
            .order_by(func.count(MovimentoContas.id).desc())
            .all()
        )
        if not resultados:
            return "Nenhum fornecedor com mais de {minimo} lançamentos neste mês.".format(minimo=minimo)

        linhas = [
            f"- {nome or 'Fornecedor sem nome'}: {qtd} lançamentos, total {self._format_currency(valor or 0)}"
            for nome, qtd, valor in resultados
        ]
        return "Fornecedores com maior recorrência neste mês:\n" + "\n".join(linhas)

    def _handle_faturados_parcelas_abertas(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        if "faturado" not in pergunta_lower:
            return None
        if "parcela" not in pergunta_lower:
            return None
        if "aberta" not in pergunta_lower and "aberto" not in pergunta_lower:
            return None

        resultados = (
            session.query(
                Pessoas.razaosocial,
                func.count(ParcelasContas.id).label("parcelas_em_aberto"),
                func.sum(ParcelasContas.valor_saldo).label("saldo_total"),
            )
            .join(MovimentoContas, MovimentoContas.faturado_id == Pessoas.id)
            .join(ParcelasContas, ParcelasContas.movimento_id == MovimentoContas.id)
            .filter(ParcelasContas.valor_saldo > 0)
            .group_by(Pessoas.id)
            .order_by(func.sum(ParcelasContas.valor_saldo).desc())
            .all()
        )
        if not resultados:
            return "Nenhum faturado possui parcelas em aberto no momento."

        linhas = [
            f"- {nome or 'Faturado sem nome'}: {qtd} parcelas em aberto somando {self._format_currency(saldo or 0)}"
            for nome, qtd, saldo in resultados
        ]
        return "Faturados com parcelas em aberto:\n" + "\n".join(linhas)

    def _handle_classificacoes_trimestre(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        if "classifica" not in pergunta_lower:
            return None
        if "trimestre" not in pergunta_lower:
            return None
        minimo = self._extract_currency_threshold(pergunta_original, 50000.0)
        inicio_trimestre = self._start_of_current_quarter()

        resultados = (
            session.query(
                Classificacao.descricao,
                func.sum(MovimentoContas.valor_total).label("total"),
            )
            .join(Classificacao.movimentos)
            .filter(Classificacao.tipo == "DESPESA")
            .filter(MovimentoContas.data_emissao >= inicio_trimestre)
            .group_by(Classificacao.id)
            .having(func.sum(MovimentoContas.valor_total) >= Decimal(str(minimo)))
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .all()
        )
        if not resultados:
            return "Nenhuma classificação atingiu valores superiores a {thr} no trimestre.".format(
                thr=self._format_currency(minimo)
            )

        linhas = [
            f"- {descricao or 'Sem descrição'}: {self._format_currency(total)}"
            for descricao, total in resultados
        ]
        return (
            f"Classificações com valores a partir de {self._format_currency(minimo)} desde o início do trimestre:\n"
            + "\n".join(linhas)
        )

    def _handle_notas_receber_mes(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        if "receber" not in pergunta_lower:
            return None
        if "nota" not in pergunta_lower:
            return None
        mes, ano = self._extract_month_year(pergunta_original)
        if mes is None or ano is None:
            return None

        registros = (
            session.query(MovimentoContas)
            .filter(
                MovimentoContas.tipo == "RECEBER",
                func.extract("month", MovimentoContas.data_emissao) == mes,
                func.extract("year", MovimentoContas.data_emissao) == ano,
            )
            .order_by(MovimentoContas.data_emissao.asc())
            .all()
        )
        if not registros:
            return "Nenhuma nota do tipo RECEBER encontrada para {mes:02d}/{ano}.".format(mes=mes, ano=ano)

        linhas = [
            "- Nota {nota} em {data} | Valor {valor} | Cliente: {cliente}".format(
                nota=mov.numero_nota_fiscal or "N/A",
                data=mov.data_emissao.strftime("%d/%m/%Y") if mov.data_emissao else "Sem data",
                valor=self._format_currency(mov.valor_total),
                cliente=(
                    (mov.faturado.razaosocial or mov.faturado.fantasia)
                    if mov.faturado and (mov.faturado.razaosocial or mov.faturado.fantasia)
                    else "Não informado"
                ),
            )
            for mov in registros
        ]
        meses_pt = [
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        ]
        nome_mes = meses_pt[mes - 1]
        return f"Notas do tipo RECEBER emitidas em {nome_mes}/{ano}:\n" + "\n".join(linhas)

    # ---------------- análises auxiliares para RAG semântico ----------------
    def _build_semantic_analysis(self, pergunta: str | None) -> str:
        if not pergunta:
            return ""
        texto = pergunta.lower()
        session: Session = self._session_factory()
        try:
            for template in self._semantic_templates:
                if not self._matches_intent(texto, template):
                    continue
                resultado = template["handler"](session, texto, pergunta)
                if resultado:
                    return resultado
        finally:
            session.close()
        return ""

    def _sem_manutencao_maquinario(
        self, session: Session, pergunta_lower: str, pergunta_original: str
    ) -> str | None:
        janela = 180
        inicio = date.today() - timedelta(days=janela)
        total_manut = (
            session.query(func.sum(MovimentoContas.valor_total))
            .outerjoin(MovimentoContas.classificacoes)
            .filter(
                MovimentoContas.data_emissao >= inicio,
                MovimentoContas.tipo == "PAGAR",
                or_(
                    Classificacao.descricao == "MANUTENÇÃO E OPERAÇÃO",
                    Classificacao.descricao.ilike("%MANUT%"),
                    Classificacao.descricao.ilike("%OPERAÇÃO%"),
                    MovimentoContas.descricao.ilike("%manut%"),
                    MovimentoContas.descricao.ilike("%maquin%"),
                ),
            )
            .scalar()
        ) or Decimal("0")

        total_geral = (
            session.query(func.sum(MovimentoContas.valor_total))
            .filter(MovimentoContas.data_emissao >= inicio, MovimentoContas.tipo == "PAGAR")
            .scalar()
        ) or Decimal("0")

        if total_geral == 0:
            return None

        percentual = float(total_manut / total_geral * 100) if total_geral else 0.0
        status = "elevado" if percentual >= 30 else "dentro do esperado"
        return (
            f"Nos últimos {janela} dias, gastos com manutenção/maquinário somaram {self._format_currency(total_manut)} "
            f"({percentual:.1f}% das despesas a pagar do período), sinalizando nível {status}."
        )

    def _sem_evolucao_insumos(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        janela = 90
        fim_atual = date.today()
        inicio_atual = fim_atual - timedelta(days=janela)
        inicio_passado = inicio_atual - timedelta(days=365)
        fim_passado = fim_atual - timedelta(days=365)

        filtros_class = or_(
            Classificacao.descricao == "INSUMOS AGRÍCOLAS",
            Classificacao.descricao.ilike("%INSUMO%"),
        )

        atual = (
            session.query(func.sum(MovimentoContas.valor_total))
            .join(MovimentoContas.classificacoes)
            .filter(MovimentoContas.data_emissao.between(inicio_atual, fim_atual), filtros_class)
            .scalar()
        ) or Decimal("0")

        passado = (
            session.query(func.sum(MovimentoContas.valor_total))
            .join(MovimentoContas.classificacoes)
            .filter(MovimentoContas.data_emissao.between(inicio_passado, fim_passado), filtros_class)
            .scalar()
        ) or Decimal("0")

        if atual == 0 and passado == 0:
            return "Não há registros suficientes de insumos agrícolas para comparar com o mesmo período anterior."

        variacao = 0.0
        if passado > 0:
            variacao = float((atual - passado) / passado * 100)
        tendencia = "alta" if variacao > 10 else "queda" if variacao < -10 else "estabilidade"

        return (
            "Insumos agrícolas nos últimos 90 dias: "
            f"{self._format_currency(atual)} versus {self._format_currency(passado)} no mesmo período do ano anterior; "
            f"variação de {variacao:.1f}% (tendência de {tendencia})."
        )

    def _sem_clientes_receita_90(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        inicio = date.today() - timedelta(days=90)
        registros = (
            session.query(
                Pessoas.razaosocial,
                func.sum(MovimentoContas.valor_total).label("receita"),
            )
            .join(MovimentoContas, MovimentoContas.faturado_id == Pessoas.id)
            .filter(MovimentoContas.tipo == "RECEBER", MovimentoContas.data_emissao >= inicio)
            .group_by(Pessoas.id)
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .limit(5)
            .all()
        )
        if not registros:
            return "Não foram encontradas receitas registradas nos últimos 90 dias."
        linhas = [
            f"- {nome or 'Cliente sem nome'}: {self._format_currency(valor)}"
            for nome, valor in registros
        ]
        return "Top clientes por receita nos últimos 90 dias:\n" + "\n".join(linhas)

    def _sem_fornecedores_atraso(self, session: Session, pergunta_lower: str, pergunta_original: str) -> str | None:
        hoje = date.today()
        resultados = (
            session.query(
                Pessoas.razaosocial,
                func.count(ParcelasContas.id).label("qtd"),
                func.sum(ParcelasContas.valor_saldo).label("saldo"),
            )
            .join(MovimentoContas, MovimentoContas.fornecedor_id == Pessoas.id)
            .join(ParcelasContas, ParcelasContas.movimento_id == MovimentoContas.id)
            .filter(ParcelasContas.valor_saldo > 0, ParcelasContas.data_vencimento < hoje)
            .group_by(Pessoas.id)
            .order_by(func.sum(ParcelasContas.valor_saldo).desc())
            .all()
        )
        if not resultados:
            return "Não há fornecedores com parcelas em atraso registradas."
        linhas = [
            f"- {nome or 'Fornecedor sem nome'}: {qtd} parcelas atrasadas somando {self._format_currency(saldo or 0)}"
            for nome, qtd, saldo in resultados
        ]
        return "Fornecedores com pagamentos atrasados:\n" + "\n".join(linhas)

    def _sem_custos_logisticos_semestre(
        self, session: Session, pergunta_lower: str, pergunta_original: str
    ) -> str | None:
        inicio = date.today() - timedelta(days=180)
        filtros_class = or_(
            Classificacao.descricao == "LOGÍSTICA AGRÍCOLA",
            Classificacao.descricao == "SERVIÇOS OPERACIONAIS",
            Classificacao.descricao.ilike("%LOGÍSTICA%"),
            Classificacao.descricao.ilike("%LOGISTICA%"),
        )
        filtros_desc = or_(
            MovimentoContas.descricao.ilike("%frete%"),
            MovimentoContas.descricao.ilike("%transporte%"),
            MovimentoContas.descricao.ilike("%logist%"),
        )
        resultados = (
            session.query(
                func.coalesce(Classificacao.descricao, "Não classificado"),
                func.sum(MovimentoContas.valor_total).label("total"),
            )
            .outerjoin(MovimentoContas.classificacoes)
            .filter(
                MovimentoContas.data_emissao >= inicio,
                MovimentoContas.tipo == "PAGAR",
                or_(filtros_class, filtros_desc),
            )
            .group_by(Classificacao.descricao)
            .order_by(func.sum(MovimentoContas.valor_total).desc())
            .all()
        )
        if not resultados:
            return "Sem registros de custos logísticos no semestre analisado."
        total_geral = sum((linha[1] or Decimal("0")) for linha in resultados)
        linhas = [
            f"- {descricao or 'Não classificado'}: {self._format_currency(total)}"
            for descricao, total in resultados
        ]
        return (
            f"Custos logísticos dos últimos 6 meses totalizam {self._format_currency(total_geral)}; principais categorias:\n"
            + "\n".join(linhas)
        )

    # ---------------- RAG Semântico ----------------
    def _retrieve_data_semantico(self, pergunta: str, k: int = 3) -> str:
        if not self._enable_chroma or self._chroma_client is None or self._embed_model is None:
            return "ChromaDB ou model de embeddings não configurado."
        query_emb = self._embed_model.encode([pergunta])[0].tolist()
        # Ensure the semantic collection exists and has data before querying embeddings.
        collection = self._get_or_create_collection()
        if collection is None:
            return "Coleção Chroma 'movimentos' não encontrada."

        try:
            total_docs = collection.count()
        except Exception:
            total_docs = 0

        if total_docs == 0:
            try:
                self.indexar_movimentos_para_chroma()
                collection = self._get_or_create_collection()
            except Exception:
                collection = None

            if collection is None:
                return self._retrieve_data_simples(pergunta)

            try:
                total_docs = collection.count()
            except Exception:
                total_docs = 0

        results = collection.query(query_embeddings=[query_emb], n_results=k, include=['metadatas', 'documents'])
        docs = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        if not docs:
            return self._retrieve_data_simples(pergunta)

        partes = []
        for i, doc in enumerate(docs):
            meta = metadatas[i] if i < len(metadatas) else {}
            partes.append(f"Documento {i+1} (id={meta.get('id')}): {doc}")

        if not partes:
            return self._retrieve_data_simples(pergunta)

        contexto_semantico = "\n".join(partes)

        # Complementa com busca simples para enriquecer contexto e evitar respostas vazias
        contexto_simples = self._retrieve_data_simples(pergunta)
        if contexto_simples and contexto_simples.strip() and contexto_simples.strip() != "Nenhum registro encontrado.":
            return f"{contexto_semantico}\n\nContexto adicional (SQL):\n{contexto_simples}"

        return contexto_semantico

    def executar_consulta_semantica(self, pergunta: str) -> str:
        analise = self._build_semantic_analysis(pergunta)
        contexto = self._retrieve_data_semantico(pergunta)
        if analise:
            contexto = f"Insights consolidados:\n{analise}\n\nContexto adicional:\n{contexto}"
        prompt = (
            f"Você é um analista financeiro. Com base **apenas** nos seguintes dados do sistema:\n\n"
            f"{contexto}\n\n"
            f"Responda a seguinte pergunta do usuário: {pergunta}\n\n"
            f"Se os dados não forem suficientes, informe que a resposta não pode ser encontrada."
        )
        api_key = self._resolve_api_key()
        resposta = self._llm_callable(prompt, api_key=api_key)
        return resposta or "Falha ao gerar resposta via LLM."

    def _resolve_api_key(self) -> str | None:
        if not self._api_key_resolver:
            return None
        try:
            return self._api_key_resolver()
        except Exception:
            return None

    # ---------------- Index script helper (opcional) ----------------
    def indexar_movimentos_para_chroma(self, k_batch: int = 1000):
        """Varredura do banco para indexar textos no ChromaDB (executar manualmente)."""
        if not self._enable_chroma or self._chroma_client is None or self._embed_model is None:
            raise RuntimeError("ChromaDB ou sentence-transformers não disponíveis no ambiente.")
        session = self._session_factory()
        try:
            rows = session.execute(select(MovimentoContas)).scalars().all()
            docs = []
            ids = []
            metadatas = []
            for movimento in rows:
                fornecedor = None
                faturado = None
                if movimento.fornecedor:
                    fornecedor = movimento.fornecedor.razaosocial or movimento.fornecedor.fantasia
                if movimento.faturado:
                    faturado = movimento.faturado.razaosocial or movimento.faturado.fantasia

                classificacoes = [c.descricao for c in movimento.classificacoes or [] if c.descricao]
                classificacao_texto = ", ".join(classificacoes) if classificacoes else "Sem classificação"

                texto = (
                    "Movimento "
                    f"{movimento.id}: nota {movimento.numero_nota_fiscal or 'N/A'}, "
                    f"emitida em {movimento.data_emissao}, valor total {movimento.valor_total}, "
                    f"descricao: {movimento.descricao or 'Sem descrição'}, "
                    f"fornecedor: {fornecedor or 'Não informado'}, "
                    f"faturado: {faturado or 'Não informado'}, "
                    f"classificação: {classificacao_texto}"
                )
                docs.append(texto)
                ids.append(str(movimento.id))
                metadatas.append({"id": movimento.id})
            collection = self._get_or_create_collection()
            if collection is None:
                raise RuntimeError("Coleção Chroma 'movimentos' não encontrada.")
            if not docs:
                return {"indexed": 0}
            embs = self._embed_model.encode(docs).tolist()
            add_fn = getattr(collection, "upsert", collection.add)
            add_fn(documents=docs, embeddings=embs, ids=ids, metadatas=metadatas)

            if hasattr(self._chroma_client, "persist"):
                self._chroma_client.persist()
            return {"indexed": len(docs)}
        finally:
            session.close()

    # --- métodos auxiliares para compatibilidade com testes antigos ---
    def consultar_simples(self, pergunta: str):
        return self.executar_consulta_simples(pergunta)

    def consultar_semantico(self, pergunta: str):
        return self.executar_consulta_semantica(pergunta)

    def indexar_movimentos(self):
        return self.indexar_movimentos_para_chroma()
