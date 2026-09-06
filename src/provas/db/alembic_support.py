"""Registra o dialeto duckdb no Alembic (que não o conhece nativamente).

Importar este módulo antes de qualquer operação Alembic contra DuckDB.
Suficiente para o nosso uso forward-only (CREATE/DROP/stamp).
"""

from alembic.ddl.impl import DefaultImpl


class DuckDBImpl(DefaultImpl):
    __dialect__ = "duckdb"
