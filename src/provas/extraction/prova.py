"""Extração multimodal de questões: uma chamada por questão, nunca a prova inteira.

Cada questão extraída é persistida em data/interim/<hash16>/questoes/qNNN.json
antes da carga — reprocessar uma questão que falhou não refaz as demais.
"""

import base64
import json
from pathlib import Path
from typing import Any

from provas.extraction.client import Prompt, carregar_prompt, extrair
from provas.models.prova import QuestaoExtraida
from provas.parsing.artifacts import ParseArtifacts, interim_dir
from provas.parsing.segmenter import SegmentoQuestao

MAX_PAGINAS_POR_CHAMADA = 3  # segurança: questão nunca deveria atravessar mais que isso


def _bloco_imagem(png: Path) -> dict[str, Any]:
    dados = base64.standard_b64encode(png.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": dados},
    }


def _conteudo_multimodal(art: ParseArtifacts, seg: SegmentoQuestao) -> list[dict[str, Any]]:
    blocos: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"Questão de número {seg.numero} (páginas {seg.pagina_inicio}-"
                f"{seg.pagina_fim}).\n\nTexto parseado do trecho:\n\n{seg.texto}"
            ),
        }
    ]
    paginas = range(
        seg.pagina_inicio, min(seg.pagina_fim, seg.pagina_inicio + MAX_PAGINAS_POR_CHAMADA - 1) + 1
    )
    for p in paginas:
        png = art.pagina_png(p)
        if png.exists():
            blocos.append({"type": "text", "text": f"Imagem da página {p}:"})
            blocos.append(_bloco_imagem(png))
    return blocos


def caminho_questao_json(hash_sha256: str, numero: int) -> Path:
    return interim_dir(hash_sha256) / "questoes" / f"q{numero:03d}.json"


def extrair_questao(
    cliente: Any,
    art: ParseArtifacts,
    seg: SegmentoQuestao,
    *,
    force: bool = False,
) -> tuple[QuestaoExtraida, Prompt]:
    """Extrai uma questão (com cache em disco por questão)."""
    prompt = carregar_prompt("questao_extracao")
    destino = caminho_questao_json(art.hash_sha256, seg.numero)
    if destino.exists() and not force:
        return QuestaoExtraida.model_validate_json(
            destino.read_text(encoding="utf-8")
        ), prompt

    resultado = extrair(
        cliente,
        prompt=prompt,
        response_model=QuestaoExtraida,
        user_content=_conteudo_multimodal(art, seg),
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    return resultado, prompt


def persistir_segmentacao(art: ParseArtifacts, segmentos: list[SegmentoQuestao]) -> None:
    payload = [
        {
            "numero": s.numero,
            "pagina_inicio": s.pagina_inicio,
            "pagina_fim": s.pagina_fim,
            "chars": len(s.texto),
        }
        for s in segmentos
    ]
    (interim_dir(art.hash_sha256) / "segmentacao.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
