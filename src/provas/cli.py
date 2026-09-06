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
        session.commit()
        typer.echo(
            f"Gabarito {tipo} aplicado: {res.aplicados} questões, "
            f"{res.anuladas} anuladas, {res.alteradas} alteradas."
        )
        if res.sem_questao_na_prova:
            typer.echo(f"AVISO: itens sem questão na prova: {res.sem_questao_na_prova}")
        if res.sem_item_no_gabarito:
            typer.echo(f"AVISO: questões sem item no gabarito: {res.sem_item_no_gabarito}")


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


if __name__ == "__main__":
    app()
