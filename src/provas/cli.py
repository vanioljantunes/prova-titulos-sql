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


if __name__ == "__main__":
    app()
