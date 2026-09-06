"""Cliente Instructor/Anthropic e carregamento de prompts versionados.

O modelo é fixo por configuração (PROVAS_MODEL), nunca decidido em código de
extração — a versão do modelo e do prompt vão juntas para a procedência.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

PROMPTS_DIR = Path("prompts")
DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 16384


@dataclass(frozen=True)
class Prompt:
    nome: str
    version: str
    texto: str


def carregar_prompt(nome: str) -> Prompt:
    """Lê prompts/<nome>.md e extrai o cabeçalho `version:` (obrigatório)."""
    caminho = PROMPTS_DIR / f"{nome}.md"
    conteudo = caminho.read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)\s*$", conteudo, flags=re.MULTILINE)
    if not m:
        raise ValueError(f"prompt {caminho} sem cabeçalho 'version:'")
    corpo = re.sub(r"\A---\n.*?\n---\n", "", conteudo, flags=re.DOTALL)
    return Prompt(nome=nome, version=m.group(1), texto=corpo.strip())


def modelo_configurado() -> str:
    return os.environ.get("PROVAS_MODEL", DEFAULT_MODEL)


def _carregar_dotenv() -> None:
    """Carrega ANTHROPIC_API_KEY de um .env na raiz do projeto, se existir."""
    env = Path(".env")
    if not env.exists():
        return
    for linha in env.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, _, valor = linha.partition("=")
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def criar_cliente() -> Any:
    """Instructor sobre Anthropic. Exige ANTHROPIC_API_KEY (ambiente ou .env)."""
    import anthropic
    import instructor

    _carregar_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY ausente. Defina no ambiente ou crie um arquivo .env "
            "na raiz do projeto com: ANTHROPIC_API_KEY=sk-ant-..."
        )
    return instructor.from_anthropic(anthropic.Anthropic())


T = TypeVar("T")


def extrair(
    cliente: Any,
    *,
    prompt: Prompt,
    response_model: type[T],
    user_content: str | list[dict[str, Any]],
    max_retries: int = 2,
) -> T:
    """Uma chamada de extração estruturada. user_content pode ser multimodal
    (lista de blocos anthropic: text + image)."""
    return cliente.chat.completions.create(  # type: ignore[no-any-return]
        model=modelo_configurado(),
        max_tokens=MAX_TOKENS,
        max_retries=max_retries,
        system=prompt.texto,
        messages=[{"role": "user", "content": user_content}],
        response_model=response_model,
    )
