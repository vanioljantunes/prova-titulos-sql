"""Layout dos artefatos intermediários em data/interim/.

Cada arquivo-fonte tem um diretório próprio, chaveado pelo prefixo do SHA-256,
para que qualquer etapa possa ser reprocessada isoladamente:

    data/interim/<hash16>/
        meta.json        # caminho original, hash completo, num_paginas, parseado_em
        parsed.md        # markdown do Docling
        pages/page_001.png ...  # páginas rasterizadas (ECG precisa de resolução)
        midia/           # recortes de mídia por questão (marco 4)
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

INTERIM_ROOT = Path("data/interim")


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def interim_dir(hash_sha256: str) -> Path:
    return INTERIM_ROOT / hash_sha256[:16]


@dataclass(frozen=True)
class ParseArtifacts:
    """Artefatos persistidos de um parse; tudo o que as etapas seguintes precisam."""

    hash_sha256: str
    markdown_path: Path
    pages_dir: Path
    num_paginas: int

    @property
    def markdown(self) -> str:
        return self.markdown_path.read_text(encoding="utf-8")

    def pagina_png(self, numero: int) -> Path:
        return self.pages_dir / f"page_{numero:03d}.png"


def gravar_meta(destino: Path, caminho_original: Path, hash_sha256: str, num_paginas: int) -> None:
    meta = {
        "caminho_original": str(caminho_original),
        "hash_sha256": hash_sha256,
        "num_paginas": num_paginas,
        "parseado_em": datetime.now(UTC).isoformat(),
    }
    (destino / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                       encoding="utf-8")


def carregar_artifacts(hash_sha256: str) -> ParseArtifacts | None:
    """Recupera artefatos de um parse anterior, se existirem (reprocesso barato)."""
    d = interim_dir(hash_sha256)
    meta_path = d / "meta.json"
    md = d / "parsed.md"
    if not (meta_path.exists() and md.exists()):
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return ParseArtifacts(
        hash_sha256=hash_sha256,
        markdown_path=md,
        pages_dir=d / "pages",
        num_paginas=int(meta["num_paginas"]),
    )
