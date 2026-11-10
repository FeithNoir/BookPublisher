"""Lectores: convierten cada formato de entrada en un ``Document``."""

from __future__ import annotations

from pathlib import Path


def read_any(path: str | Path, data: bytes | None = None) -> "Document":
    """Elige el lector por extensión: .md/.markdown, .txt, .docx."""
    from io import BytesIO

    p = Path(path)
    ext = p.suffix.lower()
    raw = data if data is not None else p.read_bytes()
    if ext in (".md", ".markdown", ".mdown"):
        from .markdown_reader import read_markdown
        doc = read_markdown(_decode(raw))
        load_local_assets(doc, p.parent)
        return doc
    if ext in (".txt", ".text", ""):
        from .text_reader import read_text
        return read_text(_decode(raw))
    if ext == ".docx":
        from .docx_reader import read_docx
        return read_docx(BytesIO(raw))
    raise ValueError(f"Formato no soportado: {ext or 'sin extensión'}. Usa .md, .txt o .docx (o importa un PDF).")


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_local_assets(doc, base: Path) -> None:
    """Carga las imágenes referenciadas con ruta relativa (junto al .md)."""
    from ..model import Image

    srcs = [b.src for b in _iter_images(doc)]
    if doc.meta.get("cover_image"):
        srcs.append(str(doc.meta["cover_image"]))
    for src in srcs:
        if src in doc.assets or src.startswith(("http://", "https://", "/assets/")):
            continue
        f = (base / src).resolve()
        try:
            if f.is_file() and base.resolve() in f.parents:
                doc.assets[src] = f.read_bytes()
        except OSError:
            continue


def _iter_images(doc):
    from ..model import Callout, Image, ListBlock, Quote

    def walk(blocks):
        for b in blocks:
            if isinstance(b, Image):
                yield b
            elif isinstance(b, (Quote, Callout)):
                yield from walk(b.blocks)
            elif isinstance(b, ListBlock):
                for it in b.items:
                    yield from walk(it.blocks)

    yield from walk(doc.front)
    for ch in doc.chapters:
        yield from walk(ch.blocks)
