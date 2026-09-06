"""Backend de extração via Claude Code CLI (`claude -p`), sem chave de API.

Usa a assinatura local do Claude Code. O prompt vai por stdin (evita limite de
linha de comando do Windows); imagens são referenciadas por caminho absoluto e
lidas pelo próprio CLI via ferramenta Read. A resposta deve ser SOMENTE JSON,
validado contra o schema Pydantic — com retry que devolve o erro de validação
ao modelo.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

TIMEOUT_S = 600
MAX_TURNS = "16"


def _montar_prompt(
    sistema: str, blocos: list[dict[str, Any]], schema_json: str, erro_anterior: str | None
) -> str:
    partes = [sistema, ""]
    for b in blocos:
        if b["type"] == "text":
            partes.append(b["text"])
        elif b["type"] == "image_path":
            caminho = str(Path(b["path"]).resolve())
            partes.append(
                f"[IMAGEM] Leia com a ferramenta Read o arquivo de imagem: {caminho}"
            )
    partes += [
        "",
        "Sua resposta final deve ser SOMENTE um objeto JSON válido (sem markdown, sem "
        "cercas de código, sem comentários) conforme este JSON Schema:",
        schema_json,
    ]
    if erro_anterior:
        partes += [
            "",
            "ATENÇÃO: sua resposta anterior falhou a validação com o erro abaixo. "
            "Corrija e devolva o JSON completo novamente:",
            erro_anterior,
        ]
    return "\n".join(partes)


def _extrair_json(texto: str) -> str:
    t = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, flags=re.DOTALL)
    if m:
        return m.group(1)
    inicio = t.find("{")
    fim = t.rfind("}")
    if inicio >= 0 and fim > inicio:
        return t[inicio : fim + 1]
    return t


def _mapear_modelo(modelo: str) -> str:
    return modelo  # IDs claude-* são aceitos diretamente pelo CLI


def extrair_via_cli(
    *,
    sistema: str,
    blocos: list[dict[str, Any]],
    response_model: type[T],
    modelo: str,
    max_retries: int = 2,
) -> T:
    schema_json = json.dumps(
        response_model.model_json_schema(), ensure_ascii=False  # type: ignore[attr-defined]
    )
    erro: str | None = None
    ultima_saida = ""
    for _tentativa in range(max_retries + 1):
        prompt = _montar_prompt(sistema, blocos, schema_json, erro)
        proc = subprocess.run(
            [
                "claude", "-p", "--output-format", "json",
                "--model", _mapear_modelo(modelo),
                "--allowedTools", "Read",
                "--max-turns", MAX_TURNS,
            ],
            input=prompt,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
            shell=(os.name == "nt"),
        )
        if proc.returncode != 0:
            erro = f"claude CLI exit={proc.returncode}: {proc.stderr[-500:]}"
            continue
        try:
            envelope = json.loads(proc.stdout)
            ultima_saida = envelope.get("result", "")
            candidato = _extrair_json(ultima_saida)
            validado: T = response_model.model_validate_json(  # type: ignore[attr-defined]
                candidato
            )
            return validado
        except Exception as e:
            erro = f"{type(e).__name__}: {e}"[:1500]
    raise RuntimeError(
        f"extração via CLI falhou após {max_retries + 1} tentativas: {erro}\n"
        f"última saída: {ultima_saida[:500]}"
    )
