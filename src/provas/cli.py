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
