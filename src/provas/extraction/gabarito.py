"""Extração de gabarito: chamada multimodal única (documentos curtos)."""

from typing import Any

from provas.extraction.client import Prompt, carregar_prompt, extrair
from provas.extraction.prova import _bloco_imagem
from provas.models.gabarito import GabaritoExtraido
from provas.parsing.artifacts import ParseArtifacts, interim_dir


def extrair_gabarito(
    cliente: Any, art: ParseArtifacts, *, caderno: str | None = None
) -> tuple[GabaritoExtraido, Prompt]:
    prompt = carregar_prompt("gabarito_extracao")
    blocos: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                (f"Extraia o gabarito do caderno: {caderno}.\n\n" if caderno else "")
                + f"Markdown do documento de gabarito:\n\n{art.markdown}"
            ),
        }
    ]
    for p in range(1, art.num_paginas + 1):
        png = art.pagina_png(p)
        if png.exists():
            blocos.append({"type": "text", "text": f"Imagem da página {p}:"})
            blocos.append(_bloco_imagem(png))

    resultado = extrair(
        cliente, prompt=prompt, response_model=GabaritoExtraido, user_content=blocos
    )
    (interim_dir(art.hash_sha256) / "gabarito.json").write_text(
        resultado.model_dump_json(indent=2), encoding="utf-8"
    )
    return resultado, prompt
