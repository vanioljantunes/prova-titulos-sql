"""Criação de engine/sessão. Trocar DuckDB→PostgreSQL = trocar PROVAS_DB_URL."""

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DB_PATH = Path("data/db/provas.duckdb")


def database_url() -> str:
    url = os.environ.get("PROVAS_DB_URL")
    if url:
        return url
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"duckdb:///{DEFAULT_DB_PATH.as_posix()}"


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url())


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
