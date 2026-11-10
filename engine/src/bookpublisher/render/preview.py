"""Vista previa rápida: compone un solo capítulo (o la portada) y lo rasteriza.

Reutiliza la caché de fragmentos de la exportación, así que mirar un capítulo
ya visto (o ya exportado) es instantáneo, y exportar después aprovecha lo que
la vista previa ya compuso.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..model import Document
from ..themes import get_theme
from ..writers.typst_writer import TypstWriter
from .normalize import fix_dialogue_dashes, normalize_titles
from .pipeline import (RenderError, RenderOptions, Runtime, _cache_paths, _compile_one, build_chunks,
                       compile_chunk, front_source)


@dataclass
class PreviewPage:
    number: int  # página dentro del fragmento (1 = primera)
    png: Path


def prepare(doc: Document, options: RenderOptions):
    theme = get_theme(options.theme)
    if options.normalize_titles:
        normalize_titles(doc)
        fix_dialogue_dashes(doc)
    doc.number_chapters()
    seen = False
    for ch in doc.chapters:
        ch.appendix = seen and not ch.numbered  # type: ignore[attr-defined]
        seen = seen or ch.numbered
    return theme, options.resolved()


def preview(doc: Document, options: RenderOptions, runtime: Runtime, target: str | int = 0,
            max_pages: int = 4, dpi: int = 110) -> dict:
    """Devuelve las primeras páginas del capítulo ``target`` (índice) o de ``"cover"``."""
    import pymupdf

    theme, opts = prepare(doc, options)
    writer = TypstWriter(doc, theme.id)
    asset_map = runtime.put_assets(doc)
    first_page = 1
    if target == "cover":
        # Índice aproximado: sin maquetar todo el libro no hay números de página reales.
        entries = _rough_entries(doc)
        src = front_source(doc, opts, writer, theme.id, entries, asset_map, True, options.toc)
        pdf = _compile_one(runtime, src, "front-preview", [])
        total_hint = None
    else:
        idx = int(target)
        if not 0 <= idx < max(1, len(doc.chapters)):
            raise RenderError(f"No existe el capítulo {idx + 1}.")
        _, chunks = build_chunks(doc, opts, writer, theme.id, asset_map)
        chunk = next(c for c in chunks if idx in c.chapters)
        pdf, meta = _cache_paths(runtime, chunk, 1)
        if not (pdf.exists() and meta.exists()):
            rel = f"work/{chunk.key}-1.typ"
            (runtime.root / rel).write_text(chunk.source.replace("@@START@@", "1"), encoding="utf-8")
            info = runtime.pool.submit(compile_chunk, rel, str(pdf) + ".tmp", True).result()
            if "error" in info:
                raise RenderError("Typst no pudo componer este capítulo: " + info["error"].splitlines()[0][:300],
                                  chapter=str(idx), detail=info.get("diagnostic", ""))
            Path(str(pdf) + ".tmp").replace(pdf)
            meta.write_text(json.dumps(info))
        info = json.loads(meta.read_text())
        marks = {int(m["idx"]): int(m["page"]) for m in info.get("marks", {}).get("chapters", [])}
        first_page = marks.get(idx, 1)
        total_hint = info.get("pages")
    out_dir = runtime.base / "previews"
    out_dir.mkdir(exist_ok=True)
    pages = []
    with pymupdf.open(pdf) as d:
        stop = min(d.page_count, first_page - 1 + max_pages)
        for pno in range(first_page - 1, stop):
            key = hashlib.sha256(f"{pdf.name}-{pno}-{dpi}".encode()).hexdigest()[:24]
            png = out_dir / f"{key}.png"
            if not png.exists():
                d[pno].get_pixmap(dpi=dpi).save(png)
            pages.append({"page": pno + 1, "png": str(png), "key": key})
        total = d.page_count
    return {"pages": pages, "chunk_pages": total_hint or total, "first_page": first_page}


def _rough_entries(doc: Document) -> list[dict]:
    from ..model import inline_text
    from ..writers.typst_writer import chapter_label, toc_label

    out = []
    for ch in doc.chapters:
        title = inline_text(ch.title).strip() or (chapter_label(ch, doc.meta) or "")
        out.append({"level": 1, "label": toc_label(ch, doc.meta) if inline_text(ch.title).strip() else "",
                    "title": title, "page": 0})
    return out
