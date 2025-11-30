import os
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import or_
from config.settings import GOOGLE_API_KEY, UPLOAD_FOLDER
from agents.AgenteExtracao.parser_service import extrair_texto_pdf
from agents.AgenteExtracao.ia_service import extrair_dados_com_llm
from agents.AgenteExtracao.utils import gerar_parcela_padrao
from agents.AgentePersistencia.processador import PersistenciaAgent
from database.connection import SessionLocal
from database.models import Classificacao, MovimentoContas, Pessoas


# ✅ lazy import — agente de consulta RAG (only loaded when /consulta is accessed)
# from agents.consulta_rag.processador import ConsultaRagAgent

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

def _resolve_api_key() -> str | None:
    return session.get("gemini_api_key") or GOOGLE_API_KEY

persistencia_agent = PersistenciaAgent()
_consulta_agent = None  # Lazy-loaded on first use

def _get_consulta_agent():
    """Lazy load ConsultaRagAgent on first access."""
    global _consulta_agent
    if _consulta_agent is None:
        from agents.consulta_rag.processador import ConsultaRagAgent
        _consulta_agent = ConsultaRagAgent(api_key_resolver=_resolve_api_key)
    return _consulta_agent
    
def _parse_decimal(valor: str | None) -> Decimal | None:
    if not valor:
        return None
    limpo = valor.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except (InvalidOperation, ValueError):
        return None

def _parse_date(data_str: str | None):
    if not data_str:
        return None
    try:
        return datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return None

def _format_currency(value) -> str:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    formatted = f"R$ {numeric:,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")

def _format_date_br(value) -> str:
    if not value:
        return ""
    try:
        return value.strftime("%d/%m/%Y")
    except AttributeError:
        return str(value)

app.jinja_env.filters['moeda'] = _format_currency
app.jinja_env.filters['data_br'] = _format_date_br


def _tokenize_search(value: str | None) -> list[str]:
    if not value:
        return []
    tokens = [item.strip() for item in re.split(r"[\s,]+", value) if item.strip()]
    return tokens


@app.route('/configurar_api_key', methods=['POST'])
def configurar_api_key():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return {"error": "JSON inválido"}, 400

    chave = ""
    if isinstance(payload, dict):
        chave = (payload.get('apiKey') or '').strip()

    if not chave:
        session.pop('gemini_api_key', None)
        return {"mensagem": "Chave removida. Defina GOOGLE_API_KEY ou informe uma nova chave."}, 200

    session['gemini_api_key'] = chave
    session.permanent = True
    return {"mensagem": "Chave configurada para esta sessão."}, 200


@app.route('/status_api_key', methods=['GET'])
def status_api_key():
    return {"hasKey": bool(_resolve_api_key())}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extrair', methods=['POST'])
def extrair():
    if 'file' not in request.files:
        return {"error": "Nenhum arquivo enviado"}, 400

    file = request.files['file']
    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        return {"error": "Arquivo inválido"}, 400

    api_key = _resolve_api_key()
    if not api_key:
        return {
            "error": "Configure a chave do Gemini antes de extrair.",
            "detalhes": "Defina GOOGLE_API_KEY ou informe sua chave na interface.",
        }, 400

    texto_pdf = extrair_texto_pdf(file)
    if not texto_pdf:
        return {"error": "Não foi possível extrair texto do PDF"}, 500

    try:
        raw_json_str = extrair_dados_com_llm(texto_pdf, api_key=api_key)
    except RuntimeError as exc:
        return {"error": str(exc)}, 400
    if not raw_json_str:
        return {"error": "Falha na comunicação com Gemini"}, 500

    clean_str = raw_json_str.replace("```json", "").replace("```", "").strip()
    try:
        dados_json = json.loads(clean_str)
    except json.JSONDecodeError:
        return {"error": "JSON inválido retornado pelo modelo", "resposta": clean_str}, 500

    dados_json = gerar_parcela_padrao(dados_json)

    verificacao = persistencia_agent.verificar_entidades(dados_json)
    dados_json["_verificacao"] = verificacao

    return dados_json


@app.route('/lancar_conta', methods=['POST'])
def lancar_conta():
    try:
        dados_json = request.get_json(force=True)
    except Exception:
        return {"error": "JSON inválido"}, 400

    if not isinstance(dados_json, dict):
        return {"error": "Payload deve ser um objeto JSON"}, 400

    dados_para_persistir = {
        chave: valor for chave, valor in dados_json.items() if not chave.startswith("_")
    }

    if not dados_para_persistir:
        return {"error": "Dados ausentes para lançamento"}, 400

    try:
        resultado_persistencia = persistencia_agent.lancar_conta_pagar(dados_para_persistir)
    except Exception as exc:
        print(f"Erro ao persistir dados: {exc}")
        return {"error": "Falha ao persistir dados", "detalhes": str(exc)}, 500

    return jsonify({
        "mensagem": "Conta lançada com sucesso",
        "resultado": resultado_persistencia,
    })

@app.route('/consulta', methods=['GET'])
def consulta_page():
    """Renderiza a página da interface de consulta RAG."""
    return render_template('consulta.html')


@app.route('/consultar_rag', methods=['POST'])
def consultar_rag():
    """Processa uma pergunta e retorna a resposta do modelo via RAG."""
    try:
        payload = request.get_json(force=True)
    except Exception:
        return {"error": "JSON inválido"}, 400

    pergunta = payload.get('pergunta')
    modo = payload.get('modo') or 'simples'

    if not pergunta or not isinstance(pergunta, str):
        return {"error": "Pergunta inválida"}, 400

    if not _resolve_api_key():
        return {
            "error": "Configure a chave do Gemini para executar consultas RAG.",
            "detalhes": "Use a seção 'Configurar chave do Gemini' ou a variável GOOGLE_API_KEY.",
        }, 400

    try:
        if modo == 'semantico':
            resposta = _get_consulta_agent().executar_consulta_semantica(pergunta)
        else:
            resposta = _get_consulta_agent().executar_consulta_simples(pergunta)
    except Exception as exc:
        print(f"Erro ao processar RAG: {exc}")
        return {"error": "Falha na consulta RAG", "detalhes": str(exc)}, 500

    return jsonify({"resposta": resposta})


# -----------------------
# CRUD - CONTAS
# -----------------------
@app.route('/contas', methods=['GET'])
def contas_page():
    session = SessionLocal()
    search = (request.args.get('q') or '').strip()
    terms = _tokenize_search(search)
    sort_field = request.args.get('sort') or 'data'
    sort_direction = request.args.get('dir') or 'desc'
    contas = []
    pessoas_opts = []
    class_opts = []
    sort_map = {
        'data': MovimentoContas.data_emissao,
        'valor': MovimentoContas.valor_total,
        'descricao': MovimentoContas.descricao,
        'nota': MovimentoContas.numero_nota_fiscal,
    }
    sort_column = sort_map.get(sort_field, sort_map['data'])
    try:
        query = session.query(MovimentoContas).filter(MovimentoContas.status == 'ATIVO')
        for term in terms:
            pattern = f"%{term}%"
            query = query.filter(
                or_(
                    MovimentoContas.descricao.ilike(pattern),
                    MovimentoContas.numero_nota_fiscal.ilike(pattern),
                )
            )

        if sort_direction == 'asc':
            query = query.order_by(sort_column.asc(), MovimentoContas.id.desc())
        else:
            query = query.order_by(sort_column.desc(), MovimentoContas.id.desc())

        registros = query.all()
        for movimento in registros:
            contas.append({
                "id": movimento.id,
                "descricao": movimento.descricao or "",
                "tipo": movimento.tipo or "",
                "numero_nota_fiscal": movimento.numero_nota_fiscal or "",
                "data_emissao": movimento.data_emissao.isoformat() if movimento.data_emissao else "",
                "data_emissao_br": _format_date_br(movimento.data_emissao),
                "valor_total": f"{float(movimento.valor_total or 0):.2f}",
                "valor_total_display": _format_currency(movimento.valor_total),
                "status": movimento.status or "",
                "fornecedor_id": movimento.fornecedor_id,
                "fornecedor_nome": (movimento.fornecedor.razaosocial or movimento.fornecedor.fantasia)
                if movimento.fornecedor
                else "",
                "faturado_id": movimento.faturado_id,
                "faturado_nome": (movimento.faturado.razaosocial or movimento.faturado.fantasia)
                if movimento.faturado
                else "",
                "classificacao_ids": [c.id for c in movimento.classificacoes],
                "classificacao_resumo": ", ".join(
                    [c.descricao for c in movimento.classificacoes if c.descricao]
                )
                or "Sem classificação",
            })

        pessoas_query = (
            session.query(Pessoas)
            .filter(Pessoas.status == 'ATIVO')
            .order_by(Pessoas.razaosocial.asc(), Pessoas.fantasia.asc())
            .all()
        )
        for pessoa in pessoas_query:
            pessoas_opts.append({
                "id": pessoa.id,
                "nome": pessoa.razaosocial or pessoa.fantasia or f"Pessoa {pessoa.id}",
                "tipo": (pessoa.tipo or '').upper(),
            })

        class_query = (
            session.query(Classificacao)
            .filter(Classificacao.status == 'ATIVO')
            .order_by(Classificacao.descricao.asc())
            .all()
        )
        for item in class_query:
            class_opts.append({
                "id": item.id,
                "descricao": item.descricao or f"Classificação {item.id}",
            })
    finally:
        session.close()

    return render_template(
        'contas.html',
        contas=contas,
        pessoas=pessoas_opts,
        classificacoes=class_opts,
        search_term=search,
        sort_field=sort_field if sort_field in sort_map else 'data',
        sort_direction='asc' if sort_direction == 'asc' else 'desc',
    )


@app.route('/contas/salvar', methods=['POST'])
def salvar_conta():
    form = request.form
    conta_id = form.get('id')
    session = SessionLocal()
    try:
        if conta_id:
            movimento = session.get(MovimentoContas, int(conta_id))
            if not movimento:
                flash('Conta não encontrada.', 'error')
                return redirect(url_for('contas_page'))
        else:
            movimento = MovimentoContas(status='ATIVO')
            session.add(movimento)

        movimento.descricao = form.get('descricao') or None
        movimento.tipo = form.get('tipo') or None
        movimento.numero_nota_fiscal = form.get('numero_nota_fiscal') or None
        movimento.data_emissao = _parse_date(form.get('data_emissao'))
        movimento.valor_total = _parse_decimal(form.get('valor_total'))
        movimento.fornecedor_id = form.get('fornecedor_id') or None
        movimento.faturado_id = form.get('faturado_id') or None

        status_form = form.get('status')
        if status_form:
            movimento.status = status_form
        elif not conta_id:
            movimento.status = 'ATIVO'

        class_ids = [int(cid) for cid in form.getlist('classificacao_ids') if cid]
        if class_ids:
            movimento.classificacoes = (
                session.query(Classificacao).filter(Classificacao.id.in_(class_ids)).all()
            )
        else:
            movimento.classificacoes = []

        session.commit()
        flash('Conta atualizada com sucesso.' if conta_id else 'Conta criada com sucesso.', 'success')
    except Exception as exc:
        session.rollback()
        flash(f'Erro ao salvar conta: {exc}', 'error')
    finally:
        session.close()

    return redirect(url_for('contas_page'))


@app.route('/contas/<int:conta_id>/excluir', methods=['POST'])
def excluir_conta(conta_id: int):
    session = SessionLocal()
    try:
        movimento = session.get(MovimentoContas, conta_id)
        if not movimento:
            flash('Conta não encontrada.', 'error')
        else:
            movimento.status = 'INATIVO'
            session.commit()
            flash('Conta marcada como INATIVO.', 'success')
    except Exception as exc:
        session.rollback()
        flash(f'Erro ao excluir conta: {exc}', 'error')
    finally:
        session.close()
    return redirect(url_for('contas_page'))


# -----------------------
# CRUD - PESSOAS
# -----------------------
@app.route('/pessoas', methods=['GET'])
def pessoas_page():
    search = (request.args.get('q') or '').strip()
    terms = _tokenize_search(search)
    categoria = (request.args.get('categoria') or 'TODOS').upper()
    sort_field = request.args.get('sort') or 'razao'
    sort_direction = request.args.get('dir') or 'asc'
    session = SessionLocal()
    pessoas = []
    sort_map = {
        'razao': Pessoas.razaosocial,
        'fantasia': Pessoas.fantasia,
        'documento': Pessoas.documento,
        'tipo': Pessoas.tipo,
    }
    sort_column = sort_map.get(sort_field, sort_map['razao'])
    try:
        query = session.query(Pessoas).filter(Pessoas.status == 'ATIVO')
        if categoria and categoria != 'TODOS':
            query = query.filter(Pessoas.tipo == categoria)
        for term in terms:
            pattern = f"%{term}%"
            query = query.filter(
                or_(
                    Pessoas.razaosocial.ilike(pattern),
                    Pessoas.fantasia.ilike(pattern),
                    Pessoas.documento.ilike(pattern),
                )
            )

        if sort_direction == 'desc':
            query = query.order_by(sort_column.desc(), Pessoas.id.desc())
        else:
            query = query.order_by(sort_column.asc(), Pessoas.id.asc())

        registros = query.all()
        for pessoa in registros:
            pessoas.append({
                "id": pessoa.id,
                "tipo": (pessoa.tipo or '').upper(),
                "razaosocial": pessoa.razaosocial or "",
                "fantasia": pessoa.fantasia or "",
                "documento": pessoa.documento or "",
                "status": pessoa.status or "",
            })
    finally:
        session.close()

    categorias = ['TODOS', 'FORNECEDOR', 'CLIENTE', 'FATURADO']
    return render_template(
        'pessoas.html',
        pessoas=pessoas,
        search_term=search,
        categoria=categoria,
        categorias=categorias,
        sort_field=sort_field if sort_field in sort_map else 'razao',
        sort_direction='desc' if sort_direction == 'desc' else 'asc',
    )


@app.route('/pessoas/salvar', methods=['POST'])
def salvar_pessoa():
    form = request.form
    pessoa_id = form.get('id')
    session = SessionLocal()
    try:
        if pessoa_id:
            pessoa = session.get(Pessoas, int(pessoa_id))
            if not pessoa:
                flash('Pessoa não encontrada.', 'error')
                return redirect(url_for('pessoas_page'))
        else:
            pessoa = Pessoas(status='ATIVO')
            session.add(pessoa)

        pessoa.tipo = (form.get('tipo') or '').upper() or None
        pessoa.razaosocial = form.get('razaosocial') or None
        pessoa.fantasia = form.get('fantasia') or None
        pessoa.documento = form.get('documento') or None

        status_form = form.get('status')
        if status_form:
            pessoa.status = status_form
        elif not pessoa.status:
            pessoa.status = 'ATIVO'

        session.commit()
        flash('Pessoa atualizada com sucesso.' if pessoa_id else 'Pessoa criada com sucesso.', 'success')
    except Exception as exc:
        session.rollback()
        flash(f'Erro ao salvar pessoa: {exc}', 'error')
    finally:
        session.close()

    return redirect(url_for('pessoas_page'))


@app.route('/pessoas/<int:pessoa_id>/excluir', methods=['POST'])
def excluir_pessoa(pessoa_id: int):
    session = SessionLocal()
    try:
        pessoa = session.get(Pessoas, pessoa_id)
        if not pessoa:
            flash('Pessoa não encontrada.', 'error')
        else:
            pessoa.status = 'INATIVO'
            session.commit()
            flash('Pessoa marcada como INATIVO.', 'success')
    except Exception as exc:
        session.rollback()
        flash(f'Erro ao excluir pessoa: {exc}', 'error')
    finally:
        session.close()
    return redirect(url_for('pessoas_page'))


# -----------------------
# CRUD - CLASSIFICAÇÕES
# -----------------------
@app.route('/classificacoes', methods=['GET'])
def classificacoes_page():
    search = (request.args.get('q') or '').strip()
    terms = _tokenize_search(search)
    tipo_filtro = (request.args.get('tipo') or 'TODOS').upper()
    sort_field = request.args.get('sort') or 'descricao'
    sort_direction = request.args.get('dir') or 'asc'
    session = SessionLocal()
    classificacoes = []
    sort_map = {
        'descricao': Classificacao.descricao,
        'tipo': Classificacao.tipo,
    }
    sort_column = sort_map.get(sort_field, sort_map['descricao'])
    try:
        query = session.query(Classificacao).filter(Classificacao.status == 'ATIVO')
        if tipo_filtro != 'TODOS':
            query = query.filter(Classificacao.tipo == tipo_filtro)
        for term in terms:
            pattern = f"%{term}%"
            query = query.filter(Classificacao.descricao.ilike(pattern))

        if sort_direction == 'desc':
            query = query.order_by(sort_column.desc(), Classificacao.id.desc())
        else:
            query = query.order_by(sort_column.asc(), Classificacao.id.asc())

        registros = query.all()
        for item in registros:
            classificacoes.append({
                "id": item.id,
                "tipo": (item.tipo or '').upper(),
                "descricao": item.descricao or "",
                "status": item.status or "",
            })
    finally:
        session.close()

    tipos = ['TODOS', 'RECEITA', 'DESPESA']
    return render_template(
        'classificacoes.html',
        classificacoes=classificacoes,
        search_term=search,
        tipo_filtro=tipo_filtro,
        tipos=tipos,
        sort_field=sort_field if sort_field in sort_map else 'descricao',
        sort_direction='desc' if sort_direction == 'desc' else 'asc',
    )


@app.route('/classificacoes/salvar', methods=['POST'])
def salvar_classificacao():
    form = request.form
    class_id = form.get('id')
    session = SessionLocal()
    try:
        if class_id:
            classificacao = session.get(Classificacao, int(class_id))
            if not classificacao:
                flash('Classificação não encontrada.', 'error')
                return redirect(url_for('classificacoes_page'))
        else:
            classificacao = Classificacao(status='ATIVO')
            session.add(classificacao)

        classificacao.tipo = (form.get('tipo') or '').upper() or None
        classificacao.descricao = form.get('descricao') or None
        status_form = form.get('status')
        if status_form:
            classificacao.status = status_form
        elif not class_id:
            classificacao.status = 'ATIVO'

        session.commit()
        flash(
            'Classificação atualizada com sucesso.' if class_id else 'Classificação criada com sucesso.',
            'success',
        )
    except Exception as exc:
        session.rollback()
        flash(f'Erro ao salvar classificação: {exc}', 'error')
    finally:
        session.close()
    return redirect(url_for('classificacoes_page'))


@app.route('/classificacoes/<int:class_id>/excluir', methods=['POST'])
def excluir_classificacao(class_id: int):
    session = SessionLocal()
    try:
        classificacao = session.get(Classificacao, class_id)
        if not classificacao:
            flash('Classificação não encontrada.', 'error')
        else:
            classificacao.status = 'INATIVO'
            session.commit()
            flash('Classificação marcada como INATIVO.', 'success')
    except Exception as exc:
        session.rollback()
        flash(f'Erro ao excluir classificação: {exc}', 'error')
    finally:
        session.close()
    return redirect(url_for('classificacoes_page'))


# Manter compatibilidade com rota antiga, se necessário
app.add_url_rule('/upload', view_func=extrair, methods=['POST'])

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug)
