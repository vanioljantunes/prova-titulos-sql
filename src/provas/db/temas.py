"""Aprovação humana de temas novos propostos pela reconciliação.

A taxonomia canônica só cresce por aqui — nunca automaticamente.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from provas.db.tables import EditalTema, Tema, Validacao
from provas.extraction.reconcile import REGRA_TEMA_NOVO


@dataclass(frozen=True)
class PropostaPendente:
    validacao_id: int
    edital_id: int
    especialidade: str
    codigo: str | None
    texto_original: str
    nivel: int
    parent_codigo: str | None
    ordem: int
    slug: str


def propostas_pendentes(session: Session, edital_id: int | None = None) -> list[PropostaPendente]:
    stmt = select(Validacao).where(
        Validacao.regra == REGRA_TEMA_NOVO, Validacao.resolvido.is_(False)
    )
    saida: list[PropostaPendente] = []
    for v in session.scalars(stmt):
        payload = json.loads(v.mensagem or "{}")
        if edital_id is not None and payload.get("edital_id") != edital_id:
            continue
        saida.append(
            PropostaPendente(
                validacao_id=v.id,
                edital_id=payload["edital_id"],
                especialidade=payload["especialidade"],
                codigo=payload.get("codigo"),
                texto_original=payload["texto_original"],
                nivel=payload.get("nivel") or 1,
                parent_codigo=payload.get("parent_codigo"),
                ordem=payload.get("ordem") or 0,
                slug=payload["slug"],
            )
        )
    saida.sort(key=lambda p: p.ordem)
    return saida


def aprovar_propostas(
    session: Session, propostas: list[PropostaPendente], *, resolvido_por: str = "humano"
) -> list[Tema]:
    """Cria os temas canônicos aprovados + edital_tema e fecha as validações.

    Resolução de pai: primeiro entre os temas criados neste lote (por codigo),
    depois na taxonomia existente da especialidade (por codigo).
    """
    criados: list[Tema] = []
    por_codigo: dict[str, Tema] = {}

    for p in propostas:
        parent_id: int | None = None
        if p.parent_codigo:
            pai = por_codigo.get(p.parent_codigo) or session.scalar(
                select(Tema).where(
                    Tema.especialidade == p.especialidade, Tema.codigo == p.parent_codigo
                )
            )
            parent_id = pai.id if pai is not None else None

        existente = session.scalar(
            select(Tema).where(Tema.especialidade == p.especialidade, Tema.slug == p.slug)
        )
        tema = existente
        if tema is None:
            tema = Tema(
                especialidade=p.especialidade,
                parent_id=parent_id,
                nivel=p.nivel,
                codigo=p.codigo,
                nome=p.texto_original,
                slug=p.slug,
            )
            session.add(tema)
            session.flush()
            criados.append(tema)
        if p.codigo:
            por_codigo[p.codigo] = tema

        session.add(
            EditalTema(
                edital_id=p.edital_id,
                tema_id=tema.id,
                texto_original=p.texto_original,
                ordem=p.ordem,
            )
        )

        v = session.get(Validacao, p.validacao_id)
        assert v is not None
        v.resolvido = True
        v.resolvido_por = resolvido_por
        v.resolvido_em = datetime.now(UTC).replace(tzinfo=None)

    session.flush()
    return criados
