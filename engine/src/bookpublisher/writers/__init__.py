"""Escritores: Markdown, DOCX y Typst (para PDF)."""

from __future__ import annotations

from pathlib import Path


def save_markdown_bundle(doc, md_path: str | Path) -> list[Path]:
    """Guarda el .md y sus imágenes en «<nombre>-imagenes/». Devuelve los archivos creados."""
    from ..model import Image
    from ..readers import _iter_images
    from .markdown_writer import write_markdown

    md_path = Path(md_path)
    folder = md_path.with_name(md_path.stem + "-imagenes")
    created = []
    rename = {}
    if doc.assets:
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in doc.assets.items():
            target = folder / Path(name).name
            target.write_bytes(data)
            created.append(target)
            rename[name] = f"{folder.name}/{Path(name).name}"
    for img in _iter_images(doc):
        if img.src in rename:
            img.src = rename[img.src]
    if doc.meta.get("cover_image") in rename:
        doc.meta["cover_image"] = rename[doc.meta["cover_image"]]
    # Las claves de assets siguen el nuevo nombre para que el documento siga siendo exportable.
    doc.assets = {rename.get(k, k): v for k, v in doc.assets.items()}
    md_path.write_text(write_markdown(doc), encoding="utf-8")
    created.insert(0, md_path)
    return created
