"""Marco 2: persistência e recuperação dos artefatos intermediários."""

import json
from pathlib import Path

import pytest

from provas.parsing import artifacts


@pytest.fixture(autouse=True)
def interim_isolado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(artifacts, "INTERIM_ROOT", tmp_path)
    return tmp_path


def test_roundtrip_meta_e_carregar(tmp_path: Path) -> None:
    h = "f" * 64
    d = artifacts.interim_dir(h)
    (d / "pages").mkdir(parents=True)
    (d / "parsed.md").write_text("# md", encoding="utf-8")
    artifacts.gravar_meta(d, Path("data/raw/x.pdf"), h, num_paginas=7)

    art = artifacts.carregar_artifacts(h)
    assert art is not None
    assert art.num_paginas == 7
    assert art.markdown == "# md"
    assert art.pagina_png(3).name == "page_003.png"

    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["hash_sha256"] == h


def test_carregar_inexistente_retorna_none() -> None:
    assert artifacts.carregar_artifacts("0" * 64) is None
