"""Extração de edital: duas chamadas separadas (metadados+calendário; temário).

Cada chamada persiste seu JSON em data/interim/<hash16>/ antes de qualquer
carga no banco — a etapa seguinte lê do disco, não da memória.
"""

from pathlib import Path
from typing import Any

from provas.extraction.client import Prompt, carregar_prompt, extrair
from provas.models.edital import ConteudoProgramatico, EditalMetadados
from provas.parsing.artifacts import ParseArtifacts, interim_dir


def _persistir(art: ParseArtifacts, nome: str, payload: str) -> Path:
    destino = interim_dir(art.hash_sha256) / f"{nome}.json"
    destino.write_text(payload, encoding="utf-8")
    return destino


def extrair_metadados(cliente: Any, art: ParseArtifacts) -> tuple[EditalMetadados, Prompt]:
    prompt = carregar_prompt("edital_metadados")
    resultado = extrair(
        cliente,
        prompt=prompt,
        response_model=EditalMetadados,
        user_content=f"Markdown do edital:\n\n{art.markdown}",
    )
    _persistir(art, "edital_metadados", resultado.model_dump_json(indent=2))
    return resultado, prompt


def extrair_conteudo_programatico(
    cliente: Any, art: ParseArtifacts
) -> tuple[ConteudoProgramatico, Prompt]:
    prompt = carregar_prompt("edital_conteudo_programatico")
    resultado = extrair(
        cliente,
        prompt=prompt,
        response_model=ConteudoProgramatico,
        user_content=f"Markdown do edital:\n\n{art.markdown}",
    )
    _persistir(art, "edital_conteudo_programatico", resultado.model_dump_json(indent=2))
    return resultado, prompt
