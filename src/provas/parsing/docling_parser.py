"""Wrapper do Docling: PDF → markdown + páginas rasterizadas em data/interim/.

Import do Docling é lazy: o pacote é pesado (torch) e só é necessário quando um
parse de fato acontece. Etapas seguintes leem apenas os artefatos em disco.
"""

from pathlib import Path

from provas.parsing.artifacts import (
    ParseArtifacts,
    carregar_artifacts,
    gravar_meta,
    interim_dir,
    sha256_arquivo,
)

# Escala de rasterização das páginas. 3.0 ≈ 216 dpi — suficiente para leitura
# de ECG/ecocardiograma nos recortes de mídia. Não reduzir sem validar no gold.
IMAGES_SCALE = 3.0


def _persistir_textos_por_pagina(doc: object, destino: Path) -> None:
    """page_texts.json: texto concatenado por página (base da segmentação de questões)."""
    import json

    por_pagina: dict[int, list[str]] = {}
    for item in getattr(doc, "texts", []):
        for prov in getattr(item, "prov", []):
            por_pagina.setdefault(prov.page_no, []).append(item.text)
            break
    payload = {str(p): "\n".join(ts) for p, ts in sorted(por_pagina.items())}
    (destino / "page_texts.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _persistir_figuras(doc: object, destino: Path) -> None:
    """pictures/pic_NNN.png + pictures.json (página, bbox) — insumo de questao_midia."""
    import json

    pics_dir = destino / "pictures"
    pics_dir.mkdir(parents=True, exist_ok=True)
    indice: list[dict[str, object]] = []
    for i, pic in enumerate(getattr(doc, "pictures", []), start=1):
        pagina, bbox = None, None
        for prov in getattr(pic, "prov", []):
            pagina = prov.page_no
            bb = prov.bbox
            bbox = [bb.l, bb.t, bb.r, bb.b]
            break
        caminho_png = None
        img = pic.get_image(doc)
        if img is not None:
            caminho_png = f"pictures/pic_{i:03d}.png"
            img.save(destino / caminho_png)
        indice.append({"ordem": i, "pagina": pagina, "bbox": bbox, "caminho": caminho_png})
    (destino / "pictures.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def parse_pdf(caminho: Path, *, force: bool = False) -> ParseArtifacts:
    """Parseia o PDF e persiste artefatos. Idempotente: se o interim do mesmo
    hash já existe e force=False, reaproveita sem reparsear."""
    caminho = Path(caminho)
    h = sha256_arquivo(caminho)

    if not force:
        existentes = carregar_artifacts(h)
        if existentes is not None:
            return existentes

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.images_scale = IMAGES_SCALE
    opts.generate_page_images = True
    opts.generate_picture_images = True

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    resultado = converter.convert(caminho)
    doc = resultado.document

    destino = interim_dir(h)
    pages_dir = destino / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = destino / "parsed.md"
    markdown_path.write_text(doc.export_to_markdown(), encoding="utf-8")

    num_paginas = len(doc.pages)
    for num, pagina in doc.pages.items():
        if pagina.image is not None and pagina.image.pil_image is not None:
            pagina.image.pil_image.save(pages_dir / f"page_{num:03d}.png")

    _persistir_textos_por_pagina(doc, destino)
    _persistir_figuras(doc, destino)
    gravar_meta(destino, caminho, h, num_paginas)
    return ParseArtifacts(
        hash_sha256=h, markdown_path=markdown_path, pages_dir=pages_dir, num_paginas=num_paginas
    )
