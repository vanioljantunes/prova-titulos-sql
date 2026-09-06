"""CLI do pipeline. Comandos são adicionados marco a marco."""

from typing import TYPE_CHECKING

import typer

from provas.db.engine import database_url

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as SASession

    from provas.db.tables import Sociedade

app = typer.Typer(help="Pipeline: PDFs de provas de título/editais → banco relacional rastreável.")


@app.callback()
def _main() -> None:
    """Mantém a CLI em modo multi-comando mesmo com um único comando registrado."""


@app.command("init-db")
def init_db() -> None:
    """Cria/atualiza o schema no banco alvo via migrações Alembic (forward-only)."""
    from alembic import command
    from alembic.config import Config

    import provas.db.alembic_support  # noqa: F401  (registra o dialeto duckdb)

    url = database_url()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    typer.echo(f"Schema em {url} atualizado para a head do Alembic.")


@app.command("parse")
def parse(
    caminho: str,
    force: bool = typer.Option(False, "--force", help="Reparseia mesmo se o interim já existir."),
) -> None:
    """(Utilitário) Parseia um PDF com Docling e grava os artefatos em data/interim/."""
    from pathlib import Path

    from provas.parsing.docling_parser import parse_pdf

    art = parse_pdf(Path(caminho), force=force)
    typer.echo(
        f"hash={art.hash_sha256[:16]} paginas={art.num_paginas} "
        f"markdown={art.markdown_path} pages={art.pages_dir}"
    )


ESPECIALIDADES_CONHECIDAS = {
    "SBC": ("Sociedade Brasileira de Cardiologia", "cardiologia"),
    "SBCM": ("Sociedade Brasileira de Clínica Médica", "clinica_medica"),
}


def _obter_sociedade(
    session: "SASession", sigla: str, especialidade: str | None
) -> "Sociedade":
    from sqlalchemy import select

    from provas.db.tables import Sociedade

    soc = session.scalar(select(Sociedade).where(Sociedade.sigla == sigla))
    if soc is not None:
        return soc
    nome, esp_padrao = ESPECIALIDADES_CONHECIDAS.get(sigla, (None, None))
    esp = especialidade or esp_padrao
    if esp is None:
        raise typer.BadParameter(
            f"Sociedade {sigla} desconhecida; informe --especialidade na primeira ingestão."
        )
    soc = Sociedade(sigla=sigla, nome=nome, especialidade=esp)
    session.add(soc)
    session.flush()
    return soc


@app.command("ingest-edital")
def ingest_edital(
    caminho: str,
    sociedade: str = typer.Option(..., "--sociedade", help="Sigla (SBC, SBCM...)."),
    especialidade: str | None = typer.Option(None, "--especialidade"),
    ano: int | None = typer.Option(None, "--ano", help="Fallback se o ano não for extraível."),
    edicao: int = typer.Option(1, "--edicao"),
    force: bool = typer.Option(False, "--force", help="Reprocessa hash já ingerido."),
) -> None:
    """Ingere um edital: parse → extração (2 chamadas) → reconciliação → carga."""
    from pathlib import Path

    from provas.db.engine import get_engine, get_session_factory
    from provas.db.fontes import registrar_arquivo_fonte
    from provas.db.loaders_edital import (
        RegistradorProveniencia,
        atualizar_vigencia,
        carregar_edital,
        carregar_reconciliacao,
        temas_canonicos,
    )
    from provas.extraction.client import criar_cliente, modelo_configurado
    from provas.extraction.edital import extrair_conteudo_programatico, extrair_metadados
    from provas.extraction.reconcile import reconciliar
    from provas.parsing.docling_parser import parse_pdf

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        soc = _obter_sociedade(session, sociedade, especialidade)
        if soc.especialidade is None:
            raise typer.BadParameter(
                f"Sociedade {sociedade} sem especialidade cadastrada; use --especialidade."
            )
        esp = soc.especialidade
        art = parse_pdf(Path(caminho), force=force)
        arq = registrar_arquivo_fonte(
            session, Path(caminho), "edital", num_paginas=art.num_paginas, force=force
        )

        cliente = criar_cliente()
        typer.echo(f"Extraindo metadados/calendário ({modelo_configurado()})...")
        meta, prompt_meta = extrair_metadados(cliente, art)
        typer.echo("Extraindo conteúdo programático...")
        conteudo, prompt_cp = extrair_conteudo_programatico(cliente, art)

        prov_meta = RegistradorProveniencia(session, arq, modelo_configurado(), prompt_meta)
        edital = carregar_edital(
            session, sociedade=soc, arquivo_fonte=arq, meta=meta, prov=prov_meta,
            ano_fallback=ano, edicao=edicao,
        )

        canonicos = temas_canonicos(session, esp)
        casados, propostas = reconciliar(conteudo.temas, canonicos)
        prov_cp = RegistradorProveniencia(session, arq, modelo_configurado(), prompt_cp)
        carregar_reconciliacao(
            session, edital=edital, especialidade=esp,
            casados=casados, propostas=propostas, prov=prov_cp,
        )
        vigente = atualizar_vigencia(session, soc.id)
        session.commit()

        typer.echo(
            f"Edital id={edital.id} ({sociedade} {edital.ano}.{edital.edicao}) carregado: "
            f"{len(meta.fases)} fases, {len(meta.cronograma)} eventos de cronograma, "
            f"{len(casados)} temas casados, {len(propostas)} temas novos propostos."
        )
        if vigente is not None:
            typer.echo(f"Edital vigente da sociedade: id={vigente.id} ({vigente.ano}).")
        if propostas:
            typer.echo("Temas novos propostos (aprovar com `provas aprovar-temas`):")
            for p in propostas:
                typer.echo(f"  - [{p.extraido.codigo or '-'}] {p.extraido.texto_original}")


@app.command("ingest-prova")
def ingest_prova(
    caminho: str,
    sociedade: str = typer.Option(..., "--sociedade"),
    ano: int = typer.Option(..., "--ano"),
    edicao: int = typer.Option(1, "--edicao"),
    caderno: str | None = typer.Option(None, "--caderno", help='ex.: "Tipo 1"'),
    num_questoes: int | None = typer.Option(
        None, "--num-questoes", help="num_questoes_declarado (do caderno/edital)."
    ),
    edital_id: int | None = typer.Option(None, "--edital-id"),
    especialidade: str | None = typer.Option(None, "--especialidade"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Ingere uma prova: parse → segmentação → extração multimodal por questão → carga."""
    from pathlib import Path

    from provas.db.engine import get_engine, get_session_factory
    from provas.db.fontes import registrar_arquivo_fonte
    from provas.db.loaders_edital import RegistradorProveniencia
    from provas.db.loaders_prova import carregar_figuras, carregar_questao, criar_prova
    from provas.extraction.client import criar_cliente, modelo_configurado
    from provas.extraction.prova import extrair_questao, persistir_segmentacao
    from provas.parsing.artifacts import interim_dir
    from provas.parsing.docling_parser import parse_pdf
    from provas.parsing.segmenter import carregar_page_texts, segmentar

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        soc = _obter_sociedade(session, sociedade, especialidade)
        art = parse_pdf(Path(caminho), force=force)
        arq = registrar_arquivo_fonte(
            session, Path(caminho), "prova", num_paginas=art.num_paginas, force=force
        )

        page_texts = carregar_page_texts(interim_dir(art.hash_sha256))
        segmentos = segmentar(page_texts)
        persistir_segmentacao(art, segmentos)
        if not segmentos:
            typer.echo("ERRO: segmentação não encontrou nenhuma questão. Abortando.", err=True)
            raise typer.Exit(2)
        typer.echo(f"Segmentação: {len(segmentos)} questões (1..{segmentos[-1].numero}).")

        prova = criar_prova(
            session, sociedade=soc, arquivo_fonte=arq, ano=ano, edicao=edicao,
            edital_id=edital_id, tipo_caderno=caderno, num_questoes_declarado=num_questoes,
        )
        figuras = carregar_figuras(interim_dir(art.hash_sha256))
        cliente = criar_cliente()
        contextos_cache: dict[str, int] = {}
        carregadas = 0
        for seg in segmentos:
            extraida, prompt = extrair_questao(cliente, art, seg, force=force)
            prov = RegistradorProveniencia(session, arq, modelo_configurado(), prompt)
            carregar_questao(
                session, prova=prova, sigla=soc.sigla, extraida=extraida,
                segmento=seg, figuras=figuras, prov=prov, contextos_cache=contextos_cache,
            )
            carregadas += 1
            if carregadas % 10 == 0:
                typer.echo(f"  {carregadas}/{len(segmentos)} questões extraídas...")
        from provas.validation.regras import validar_prova

        e, a = validar_prova(session, prova)
        typer.echo(f"Validação automática: {e} erros, {a} avisos.")
        session.commit()
        typer.echo(
            f"Prova id={prova.id} carregada: {carregadas} questões, "
            f"{len(contextos_cache)} contextos, "
            f"{sum(1 for f in figuras if f.usada)}/{len(figuras)} figuras associadas. "
            f"Gabaritos permanecem nulos (use ingest-gabarito)."
        )


@app.command("ingest-gabarito")
def ingest_gabarito(
    caminho: str,
    prova_id: int = typer.Option(..., "--prova-id"),
    tipo: str = typer.Option(..., "--tipo", help="preliminar | definitivo"),
    caderno: str | None = typer.Option(
        None, "--caderno", help="Caderno a extrair, se houver vários."
    ),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Ingere um gabarito e reconcilia com as questões da prova."""
    from pathlib import Path

    from provas.db.engine import get_engine, get_session_factory
    from provas.db.fontes import registrar_arquivo_fonte
    from provas.db.loaders_edital import RegistradorProveniencia
    from provas.db.loaders_gabarito import reconciliar_gabarito
    from provas.db.tables import Prova
    from provas.extraction.client import criar_cliente, modelo_configurado
    from provas.extraction.gabarito import extrair_gabarito
    from provas.parsing.docling_parser import parse_pdf

    if tipo not in ("preliminar", "definitivo"):
        raise typer.BadParameter("--tipo deve ser preliminar ou definitivo")

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        prova = session.get(Prova, prova_id)
        if prova is None:
            raise typer.BadParameter(f"prova id={prova_id} não existe")
        art = parse_pdf(Path(caminho), force=force)
        arq = registrar_arquivo_fonte(
            session, Path(caminho), f"gabarito_{tipo}",
            num_paginas=art.num_paginas, force=force,
        )
        cliente = criar_cliente()
        typer.echo(f"Extraindo gabarito ({modelo_configurado()})...")
        gab, prompt = extrair_gabarito(cliente, art, caderno=caderno)
        prov = RegistradorProveniencia(session, arq, modelo_configurado(), prompt)
        res = reconciliar_gabarito(session, prova=prova, gabarito=gab, tipo=tipo, prov=prov)
        from provas.validation.regras import validar_prova

        e, a = validar_prova(session, prova)
        typer.echo(f"Validação automática: {e} erros, {a} avisos.")
        session.commit()
        typer.echo(
            f"Gabarito {tipo} aplicado: {res.aplicados} questões, "
            f"{res.anuladas} anuladas, {res.alteradas} alteradas."
        )
        if res.sem_questao_na_prova:
            typer.echo(f"AVISO: itens sem questão na prova: {res.sem_questao_na_prova}")
        if res.sem_item_no_gabarito:
            typer.echo(f"AVISO: questões sem item no gabarito: {res.sem_item_no_gabarito}")


@app.command("classificar-temas")
def classificar_temas(
    prova_id: int = typer.Option(..., "--prova-id"),
    force: bool = typer.Option(False, "--force", help="Reclassifica ignorando o cache."),
) -> None:
    """Classifica as questões da prova contra o vocabulário do edital vigente."""
    from sqlalchemy import select

    from provas.db.engine import get_engine, get_session_factory
    from provas.db.loaders_classificacao import aplicar_classificacao
    from provas.db.tables import Prova, Questao
    from provas.extraction.classificar import (
        classificar_questao,
        persistir_vocabulario_usado,
        vocabulario_do_edital_vigente,
    )
    from provas.extraction.client import criar_cliente, modelo_configurado

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        prova = session.get(Prova, prova_id)
        if prova is None:
            raise typer.BadParameter(f"prova id={prova_id} não existe")
        vigente, vocabulario = vocabulario_do_edital_vigente(session, prova.sociedade_id)
        if vigente is None or not vocabulario:
            typer.echo(
                "ERRO: não há edital vigente com conteúdo programático para esta "
                "sociedade. Ingira um edital (e aprove os temas) antes de classificar.",
                err=True,
            )
            raise typer.Exit(2)
        persistir_vocabulario_usado(prova_id, vocabulario)
        typer.echo(
            f"Vocabulário: {len(vocabulario)} temas do edital id={vigente.id} "
            f"({vigente.ano}). Modelo: {modelo_configurado()}."
        )

        questoes = session.scalars(
            select(Questao).where(Questao.prova_id == prova_id).order_by(Questao.numero)
        ).all()
        cliente = criar_cliente()
        nao_mapeadas = 0
        baixa_conf = 0
        for i, q in enumerate(questoes, start=1):
            resultado, _prompt = classificar_questao(
                cliente, session, q, vocabulario, force=force
            )
            aplicar_classificacao(session, q, resultado, modelo=modelo_configurado())
            if resultado.tema_principal_id is None:
                nao_mapeadas += 1
            elif resultado.confianca < 0.7:
                baixa_conf += 1
            if i % 10 == 0:
                typer.echo(f"  {i}/{len(questoes)} classificadas...")
        if prova.status == "gabarito_carregado":
            prova.status = "classificada"
        from provas.validation.regras import validar_prova

        e, a = validar_prova(session, prova)
        typer.echo(f"Validação automática: {e} erros, {a} avisos.")
        session.commit()
        typer.echo(
            f"{len(questoes)} questões classificadas: {nao_mapeadas} tema_nao_mapeado, "
            f"{baixa_conf} com confiança < 0.7 (ambas na fila de revisão)."
        )


@app.command("aprovar-temas")
def aprovar_temas(
    edital_id: int | None = typer.Option(None, "--edital-id"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Aprova sem confirmação interativa."),
) -> None:
    """Aprova temas novos propostos, criando-os na taxonomia canônica."""
    from provas.db.engine import get_engine, get_session_factory
    from provas.db.temas import aprovar_propostas, propostas_pendentes

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        pendentes = propostas_pendentes(session, edital_id)
        if not pendentes:
            typer.echo("Nenhuma proposta pendente.")
            raise typer.Exit(0)
        typer.echo(f"{len(pendentes)} propostas pendentes:")
        for p in pendentes:
            typer.echo(
                f"  - edital={p.edital_id} nivel={p.nivel} "
                f"[{p.codigo or '-'}] {p.texto_original}"
            )
        if not yes and not typer.confirm("Aprovar TODAS as propostas acima?"):
            typer.echo("Nada aprovado.")
            raise typer.Exit(1)
        criados = aprovar_propostas(session, pendentes)
        session.commit()
        typer.echo(f"{len(criados)} temas canônicos criados; propostas resolvidas.")


@app.command("validate")
def validate(
    prova_id: int | None = typer.Option(None, "--prova-id", help="Omitir = todas as provas."),
) -> None:
    """Roda a camada de validação e grava os achados em validacao."""
    from sqlalchemy import select

    from provas.db.engine import get_engine, get_session_factory
    from provas.db.tables import Prova
    from provas.validation.regras import validar_prova

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        if prova_id is not None:
            alvo = session.get(Prova, prova_id)
            if alvo is None:
                raise typer.BadParameter(f"prova id={prova_id} não existe")
            provas_alvo = [alvo]
        else:
            provas_alvo = list(session.scalars(select(Prova)))
        if not provas_alvo:
            typer.echo("Nenhuma prova no banco.")
            raise typer.Exit(0)
        total_e = total_a = 0
        for p in provas_alvo:
            e, a = validar_prova(session, p)
            total_e += e
            total_a += a
            typer.echo(f"prova id={p.id} ({p.ano}): {e} erros, {a} avisos → status={p.status}")
        session.commit()
        typer.echo(f"Total: {total_e} erros, {total_a} avisos.")
        if total_e:
            raise typer.Exit(1)


@app.command("revisar")
def revisar(
    regra: str | None = typer.Option(None, "--regra", help="Filtra por nome de regra."),
    resolver: int | None = typer.Option(
        None, "--resolver", help="ID da linha de validacao a fechar (marca revisada_por_humano)."
    ),
    resolvido_por: str = typer.Option("humano", "--por"),
) -> None:
    """Fila de pendências agrupada por regra; --resolver fecha uma pendência."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from provas.db.engine import get_engine, get_session_factory
    from provas.db.tables import Questao, Validacao

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        if resolver is not None:
            v = session.get(Validacao, resolver)
            if v is None:
                raise typer.BadParameter(f"validacao id={resolver} não existe")
            v.resolvido = True
            v.resolvido_por = resolvido_por
            v.resolvido_em = datetime.now(UTC).replace(tzinfo=None)
            if v.tabela == "questao" and v.registro_id is not None:
                q = session.get(Questao, v.registro_id)
                if q is not None:
                    q.revisada_por_humano = True
            session.commit()
            typer.echo(f"validacao id={resolver} ({v.regra}) resolvida por {resolvido_por}.")
            return

        stmt = select(Validacao).where(Validacao.resolvido.is_(False))
        if regra:
            stmt = stmt.where(Validacao.regra == regra)
        pendentes = list(session.scalars(stmt.order_by(Validacao.regra, Validacao.id)))
        if not pendentes:
            typer.echo("Fila vazia.")
            return
        atual = None
        for v in pendentes:
            if v.regra != atual:
                atual = v.regra
                n = sum(1 for x in pendentes if x.regra == atual)
                typer.echo(f"\n== {atual} ({n}) ==")
            typer.echo(f"  [{v.id}] ({v.severidade}) {v.mensagem}")
        typer.echo(f"\n{len(pendentes)} pendências. Fechar: provas revisar --resolver <ID>")


@app.command("export")
def export(
    formato: str = typer.Option(..., "--formato", help="csv | parquet"),
    saida: str = typer.Option(..., "--saida", help="Diretório de saída."),
) -> None:
    """Exporta as tabelas + visão achatada de questões (COPY nativo do DuckDB)."""
    from pathlib import Path

    from sqlalchemy import text

    from provas.db.engine import get_engine

    if formato not in ("csv", "parquet"):
        raise typer.BadParameter("--formato deve ser csv ou parquet")
    destino = Path(saida)
    destino.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    if engine.dialect.name != "duckdb":
        raise typer.BadParameter(
            "export usa COPY nativo do DuckDB; para outro banco, exporte via SQL direto."
        )
    tabelas = [
        "sociedade", "arquivo_fonte", "edital", "edital_fase", "edital_cronograma",
        "tema", "edital_tema", "prova", "contexto", "questao", "alternativa",
        "questao_midia", "questao_tema", "proveniencia", "validacao",
    ]
    visao_flat = """
        SELECT q.identificador, s.sigla AS sociedade, p.ano, p.edicao, q.numero,
               q.tipo, q.enunciado, c.texto AS contexto,
               q.gabarito_preliminar, q.gabarito_oficial, q.status,
               t.nome AS tema_principal, qt.confianca AS tema_confianca,
               q.revisada_por_humano
        FROM questao q
        JOIN prova p ON p.id = q.prova_id
        JOIN sociedade s ON s.id = p.sociedade_id
        LEFT JOIN contexto c ON c.id = q.contexto_id
        LEFT JOIN questao_tema qt ON qt.questao_id = q.id AND qt.principal
        LEFT JOIN tema t ON t.id = qt.tema_id
    """
    opts = "(HEADER, DELIMITER ',')" if formato == "csv" else "(FORMAT PARQUET)"
    with engine.connect() as conn:
        for tabela in tabelas:
            alvo = (destino / f"{tabela}.{formato}").as_posix()
            conn.execute(text(f"COPY (SELECT * FROM {tabela}) TO '{alvo}' {opts}"))
        alvo = (destino / f"questoes_flat.{formato}").as_posix()
        conn.execute(text(f"COPY ({visao_flat}) TO '{alvo}' {opts}"))
    typer.echo(f"{len(tabelas) + 1} arquivos {formato} escritos em {destino}.")


@app.command("stats")
def stats() -> None:
    """Números do banco: questões por sociedade/ano, temas, anuladas, revisão."""
    from sqlalchemy import text

    from provas.db.engine import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        typer.echo("== Questões por sociedade/ano ==")
        for sigla, ano, n in conn.execute(text("""
            SELECT s.sigla, p.ano, count(*) FROM questao q
            JOIN prova p ON p.id = q.prova_id JOIN sociedade s ON s.id = p.sociedade_id
            GROUP BY s.sigla, p.ano ORDER BY s.sigla, p.ano
        """)):
            typer.echo(f"  {sigla} {ano}: {n}")

        typer.echo("== Distribuição por tema (principal) ==")
        for nome, n in conn.execute(text("""
            SELECT t.nome, count(*) FROM questao_tema qt
            JOIN tema t ON t.id = qt.tema_id WHERE qt.principal
            GROUP BY t.nome ORDER BY count(*) DESC LIMIT 20
        """)):
            typer.echo(f"  {n:4d}  {nome}")

        total = conn.execute(text("SELECT count(*) FROM questao")).scalar() or 0
        if total:
            anuladas = conn.execute(
                text("SELECT count(*) FROM questao WHERE status='anulada'")
            ).scalar() or 0
            revisadas = conn.execute(
                text("SELECT count(*) FROM questao WHERE revisada_por_humano")
            ).scalar() or 0
            typer.echo(f"== Totais ==\n  questões: {total}")
            typer.echo(f"  anuladas: {anuladas} ({100 * anuladas / total:.1f}%)")
            typer.echo(f"  revisadas por humano: {revisadas} ({100 * revisadas / total:.1f}%)")

        typer.echo("== Pendências abertas ==")
        for sev, n in conn.execute(text("""
            SELECT severidade, count(*) FROM validacao WHERE NOT resolvido
            GROUP BY severidade ORDER BY severidade
        """)):
            typer.echo(f"  {sev}: {n}")


@app.command("avaliar-gold")
def avaliar_gold(
    prova_id: int = typer.Option(..., "--prova-id"),
    gold: str = typer.Option(..., "--gold", help="Arquivo JSON do padrão-ouro."),
    saida: str | None = typer.Option(None, "--saida", help="Grava o relatório JSON aqui."),
) -> None:
    """Compara a extração automática com o padrão-ouro transcrito à mão."""
    import json
    from pathlib import Path

    from provas.db.engine import get_engine, get_session_factory
    from provas.validation.gold import avaliar, carregar_gold

    engine = get_engine()
    factory = get_session_factory(engine)
    with factory() as session:
        rel = avaliar(session, prova_id, carregar_gold(Path(gold)))
    d = rel.como_dict()
    typer.echo(
        f"Questões: gold={d['questoes_gold']} extraídas={d['questoes_extraidas']} "
        f"faltando={d['questoes_faltando'] or 'nenhuma'}"
    )
    for grupo in ("categoricos", "textuais", "estruturais"):
        typer.echo(f"== {grupo} ==")
        for campo, m in d[grupo].items():
            typer.echo(
                f"  {campo:22s} n={m['total']:4d} exata={m['acuracia_exata']:.1%} "
                f"omissão={m['taxa_omissao']:.1%} erro={m['taxa_erro']:.1%}"
            )
    if saida:
        Path(saida).write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        typer.echo(f"Relatório gravado em {saida}.")


if __name__ == "__main__":
    app()
