"""Segmentação determinística de questões a partir dos textos por página.

Passada barata SEM LLM: encontra o início de cada questão (número, página,
offset). A extração (marco 4) então processa uma questão por chamada — nunca a
prova inteira, que é onde as omissões acontecem.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

# "QUESTÃO 12", "▪ QUESTÃO 12", "Questão 12.", "12.", "12)", "12 -" no início de linha
# (PDFs reais trazem bullets/símbolos antes do rótulo — ex.: caderno SBCM 2026)
_PADRAO_QUESTAO = re.compile(
    r"^[\s▪•·◦‣∙■□♦>*]*(?:QUEST[ÃA]O\s+)?(\d{1,3})\s*[\.\)\-–:]?\s+",  # noqa: RUF001
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class SegmentoQuestao:
    numero: int
    pagina_inicio: int
    pagina_fim: int
    texto: str  # trecho do texto entre o início desta questão e o da próxima


def carregar_page_texts(interim: Path) -> dict[int, str]:
    payload = json.loads((interim / "page_texts.json").read_text(encoding="utf-8"))
    return {int(k): v for k, v in payload.items()}


def segmentar(page_texts: dict[int, str], *, max_questao: int = 200) -> list[SegmentoQuestao]:
    """Varre as páginas em ordem e corta o texto nos inícios de questão.

    Heurística de sanidade: a numeração deve ser estritamente crescente
    (tolerando saltos); candidatos fora de sequência são ignorados como
    falsos positivos (ex.: "10." numa tabela).
    """
    marcas: list[tuple[int, int, int]] = []  # (numero, pagina, offset_global)
    corpo: list[str] = []
    offset = 0
    offsets_pagina: list[tuple[int, int]] = []  # (offset_inicial, pagina)

    for pagina in sorted(page_texts):
        texto = page_texts[pagina]
        offsets_pagina.append((offset, pagina))
        corpo.append(texto)
        for m in _PADRAO_QUESTAO.finditer(texto):
            numero = int(m.group(1))
            if 1 <= numero <= max_questao:
                marcas.append((numero, pagina, offset + m.start()))
        offset += len(texto) + 1
    texto_total = "\n".join(corpo)

    # filtra para sequência crescente começando do menor candidato
    sequencia: list[tuple[int, int, int]] = []
    esperado = None
    for numero, pagina, off in marcas:
        if esperado is None:
            if numero == 1:
                sequencia.append((numero, pagina, off))
                esperado = 2
        elif numero == esperado:
            sequencia.append((numero, pagina, off))
            esperado += 1

    segmentos: list[SegmentoQuestao] = []
    for i, (numero, pagina, off) in enumerate(sequencia):
        fim = sequencia[i + 1][2] if i + 1 < len(sequencia) else len(texto_total)
        pagina_fim = (
            sequencia[i + 1][1] if i + 1 < len(sequencia) else max(page_texts, default=pagina)
        )
        segmentos.append(
            SegmentoQuestao(
                numero=numero,
                pagina_inicio=pagina,
                pagina_fim=max(pagina, pagina_fim),
                texto=texto_total[off:fim].strip(),
            )
        )
    return segmentos
