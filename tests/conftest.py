"""Fixtures compartilhadas: banco DuckDB em memória com o schema completo."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

import provas.db.tables  # noqa: F401
from provas.db.base import Base


@pytest.fixture()
def engine() -> Iterator[Engine]:
    eng = create_engine("duckdb:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s
