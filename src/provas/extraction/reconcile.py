"""Reconciliação do conteúdo programático extraído com a taxonomia canônica.

Casamento confiante → linha em edital_tema (mesmo tema_id, série histórica
preservada). Sem casamento → proposta em validacao (aviso); o tema canônico
NUNCA é criado automaticamente — só via `provas aprovar-temas`.
"""

import json
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from provas.models.edital import TemaExtraido

LIMIAR_CONFIANTE = 92.0  # token_sort_ratio; abaixo disso vira proposta

REGRA_TEMA_NOVO = "tema_novo_proposto"


def slugify(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto)
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


@dataclass(frozen=True)
class TemaCanonico:
    id: int
    nome: str
    slug: str


@dataclass(frozen=True)
class Casamento:
    extraido: TemaExtraido
    tema_id: int
    score: float


@dataclass(frozen=True)
class Proposta:
    extraido: TemaExtraido
    melhor_candidato_id: int | None
    melhor_score: float

    def payload_json(self, edital_id: int, especialidade: str) -> str:
        return json.dumps(
            {
                "edital_id": edital_id,
                "especialidade": especialidade,
                "codigo": self.extraido.codigo,
                "texto_original": self.extraido.texto_original,
                "nivel": self.extraido.nivel,
                "parent_codigo": self.extraido.parent_codigo,
                "ordem": self.extraido.ordem,
                "pagina": self.extraido.pagina,
                "slug": slugify(self.extraido.texto_original),
                "melhor_candidato_id": self.melhor_candidato_id,
                "melhor_score": self.melhor_score,
            },
            ensure_ascii=False,
        )


def reconciliar(
    extraidos: list[TemaExtraido], canonicos: list[TemaCanonico]
) -> tuple[list[Casamento], list[Proposta]]:
    """Casa cada tema extraído com a taxonomia canônica, de forma determinística."""
    casados: list[Casamento] = []
    propostas: list[Proposta] = []
    por_slug = {c.slug: c for c in canonicos}

    for ext in extraidos:
        slug = slugify(ext.texto_original)
        exato = por_slug.get(slug)
        if exato is not None:
            casados.append(Casamento(extraido=ext, tema_id=exato.id, score=100.0))
            continue

        melhor: TemaCanonico | None = None
        melhor_score = 0.0
        for cand in canonicos:
            score = fuzz.token_sort_ratio(slug, cand.slug)
            if score > melhor_score:
                melhor, melhor_score = cand, score

        if melhor is not None and melhor_score >= LIMIAR_CONFIANTE:
            casados.append(Casamento(extraido=ext, tema_id=melhor.id, score=melhor_score))
        else:
            propostas.append(
                Proposta(
                    extraido=ext,
                    melhor_candidato_id=melhor.id if melhor else None,
                    melhor_score=melhor_score,
                )
            )
    return casados, propostas
