import threading

import pymupdf
import pytest

from bookpublisher.readers import read_any
from bookpublisher.readers.pdf_reader import PdfImportError, read_pdf
from bookpublisher.render.pipeline import ExportCancelled, RenderOptions, export_pdf
from bookpublisher.render.preview import preview
from bookpublisher.themes import all_themes


@pytest.mark.parametrize("theme", list(all_themes()))
def test_every_theme_exports(theme, samples, runtime, tmp_path):
    doc = read_any(samples / "guia-formato.md")
    out = tmp_path / f"{theme}.pdf"
    res = export_pdf(doc, RenderOptions(theme=theme), out, runtime)
    assert res.pages >= 4 and out.exists()
    with pymupdf.open(out) as d:
        assert d.page_count == res.pages
        assert len(d.get_toc()) >= 4  # marcadores por capítulo
        text = "".join(p.get_text() for p in d)
    assert "Bloques especiales" in text


def test_progress_events_and_cache(samples, runtime, tmp_path):
    events = []
    doc = read_any(samples / "quijote-ejemplo.md")
    r1 = export_pdf(doc, RenderOptions(theme="novela"), tmp_path / "a.pdf", runtime, progress=events.append)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "plan" and kinds[-1] == "done" and "chunk" in kinds
    chunk = [e for e in events if e["type"] == "chunk"]
    assert chunk[-1]["words_done"] == chunk[-1]["words_total"]
    r2 = export_pdf(read_any(samples / "quijote-ejemplo.md"), RenderOptions(theme="novela"), tmp_path / "b.pdf", runtime)
    assert r2.cached_chunks == r2.chunks and r2.pages == r1.pages
    # Recto: los capítulos abren en página impar.
    with pymupdf.open(tmp_path / "a.pdf") as d:
        starts = [p for lvl, t, p in d.get_toc() if t != "Portada e índice"]
    assert all(p % 2 == 1 for p in starts)


def test_cancel(samples, runtime, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ExportCancelled):
        export_pdf(read_any(samples / "quijote-ejemplo.md"), RenderOptions(theme="sencillo", font_size=9),
                   tmp_path / "c.pdf", runtime, cancel=cancel)


def test_preview(samples, runtime):
    doc = read_any(samples / "quijote-ejemplo.md")
    r = preview(doc, RenderOptions(theme="codice"), runtime, 2, max_pages=2)
    assert len(r["pages"]) == 2 and r["first_page"] > 1


def test_pdf_import_roundtrip(samples, runtime, tmp_path):
    """Exporta la muestra con el Códice y la vuelve a importar: títulos, sin folios, sin cabeceras."""
    out = tmp_path / "codice.pdf"
    export_pdf(read_any(samples / "codice-ejemplo.md"), RenderOptions(theme="codice"), out, runtime)
    doc, rep = read_pdf(str(out))
    titles = [t for ch in doc.chapters for t in [ch.title]]
    assert len(doc.chapters) >= 4 and titles
    assert rep.removed_headers  # «· ORDENANZAS DE LA COFRADÍA DEL TINTERO ·»
    assert doc.meta.get("title", "").upper().startswith("ORDENANZAS")
    from bookpublisher.writers.markdown_writer import write_markdown
    md = write_markdown(doc)
    assert "Pendiente de consultar" in md
    assert "tinta se prepara cada luna nueva" in md


def test_rejects_non_pdf(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"hola")
    with pytest.raises(PdfImportError):
        read_pdf(str(p))
