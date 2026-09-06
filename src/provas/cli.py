"""CLI do pipeline. Comandos são adicionados marco a marco."""

import typer

from provas.db.engine import database_url

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


if __name__ == "__main__":
    app()
