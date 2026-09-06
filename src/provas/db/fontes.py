"""Registro de arquivos-fonte com deduplicação por SHA-256 (idempotência)."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.tables import ArquivoFonte
from provas.parsing.artifacts import sha256_arquivo

TIPOS_VALIDOS = {"edital", "prova", "gabarito_preliminar", "gabarito_definitivo", "retificacao"}


class FonteJaIngeridaError(Exception):
    """Hash já registrado; reprocessar exige --force explícito."""

    def __init__(self, existente: ArquivoFonte) -> None:
        self.existente = existente
        super().__init__(
            f"Arquivo com hash {existente.hash_sha256[:16]}… já ingerido "
            f"(id={existente.id}, caminho={existente.caminho}). Use --force para reprocessar."
        )


def registrar_arquivo_fonte(
    session: Session,
    caminho: Path,
    tipo: str,
    *,
    num_paginas: int | None = None,
    force: bool = False,
) -> ArquivoFonte:
    """Registra (ou recupera, com force=True) o arquivo-fonte.

    Nunca duplica: com force, o registro existente é reaproveitado e o pipeline
    fica livre para reprocessar as etapas seguintes em cima dele (upsert).
    """
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"tipo inválido: {tipo!r}; esperado um de {sorted(TIPOS_VALIDOS)}")

    caminho = Path(caminho)
    h = sha256_arquivo(caminho)
    existente = session.scalar(select(ArquivoFonte).where(ArquivoFonte.hash_sha256 == h))
    if existente is not None:
        if not force:
            raise FonteJaIngeridaError(existente)
        existente.caminho = str(caminho)
        if num_paginas is not None:
            existente.num_paginas = num_paginas
        session.flush()
        return existente

    arq = ArquivoFonte(
        caminho=str(caminho), hash_sha256=h, tipo=tipo, num_paginas=num_paginas
    )
    session.add(arq)
    session.flush()
    return arq
