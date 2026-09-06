"""Ambiente Alembic.

Convenção do projeto: migrações FORWARD-ONLY (CREATE/DROP/recriar tabela).
DuckDB não suporta a maior parte de ALTER TABLE; nunca escrever migração que
altere constraints in-place. Downgrades não são suportados.
"""

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

import provas.db.alembic_support
import provas.db.tables  # noqa: F401  (registra as tabelas na metadata)
from provas.db.base import Base

config = context.config

env_url = os.environ.get("PROVAS_DB_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
