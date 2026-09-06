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

    gravar_meta(destino, caminho, h, num_paginas)
    return ParseArtifacts(
        hash_sha256=h, markdown_path=markdown_path, pages_dir=pages_dir, num_paginas=num_paginas
    )
