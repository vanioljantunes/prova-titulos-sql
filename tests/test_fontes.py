"""Marco 2: registro de arquivo_fonte com dedup por hash e semântica de --force."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from provas.db.fontes import FonteJaIngeridaError, registrar_arquivo_fonte
from provas.parsing.artifacts import sha256_arquivo


@pytest.fixture()
def pdf_falso(tmp_path: Path) -> Path:
    p = tmp_path / "prova.pdf"
    p.write_bytes(b"%PDF-1.7 conteudo de teste para hash")
    return p


def test_sha256_estavel(pdf_falso: Path) -> None:
    assert sha256_arquivo(pdf_falso) == sha256_arquivo(pdf_falso)
    assert len(sha256_arquivo(pdf_falso)) == 64


def test_registro_novo(session: Session, pdf_falso: Path) -> None:
    arq = registrar_arquivo_fonte(session, pdf_falso, "prova", num_paginas=10)
    assert arq.id is not None
    assert arq.hash_sha256 == sha256_arquivo(pdf_falso)
    assert arq.num_paginas == 10


def test_hash_duplicado_aborta_sem_force(session: Session, pdf_falso: Path) -> None:
    registrar_arquivo_fonte(session, pdf_falso, "prova")
    with pytest.raises(FonteJaIngeridaError):
        registrar_arquivo_fonte(session, pdf_falso, "prova")


def test_force_reaproveita_registro_sem_duplicar(session: Session, pdf_falso: Path) -> None:
    a1 = registrar_arquivo_fonte(session, pdf_falso, "prova")
    copia = pdf_falso.rename(pdf_falso.with_name("renomeada.pdf"))
    a2 = registrar_arquivo_fonte(session, copia, "prova", force=True)
    assert a2.id == a1.id  # upsert, nunca segunda linha
    assert a2.caminho.endswith("renomeada.pdf")


def test_tipo_invalido_rejeitado(session: Session, pdf_falso: Path) -> None:
    with pytest.raises(ValueError, match="tipo inválido"):
        registrar_arquivo_fonte(session, pdf_falso, "gabarito")
