import io

import docx

from bookpublisher.readers import read_any
from bookpublisher.readers.docx_reader import read_docx
from bookpublisher.readers.markdown_reader import read_markdown
from bookpublisher.writers.docx_writer import write_docx
from bookpublisher.writers.markdown_writer import write_markdown
from bookpublisher.writers.typst_writer import esc


def test_typst_escaping():
    s = esc("a #b $c *d* _e_ @f <g> [h] \\ ~ `x`")
    for ch in "#$*_@<>[]`~":
        assert "\\" + ch in s


def test_dialogue_joiner():
    assert esc("—Hola")[1] == "\u2060"


def test_markdown_roundtrip(samples):
    doc = read_any(samples / "codice-ejemplo.md")
    md = write_markdown(doc)
    again = read_markdown(md)
    assert len(again.chapters) == len(doc.chapters)
    assert "Pendiente de consultar" in md and "{.pendiente}" in md


def test_docx_roundtrip(samples):
    doc = read_any(samples / "guia-formato.md")
    buf = io.BytesIO()
    write_docx(doc, buf)
    d = docx.Document(io.BytesIO(buf.getvalue()))
    styles = {p.style.name for p in d.paragraphs}
    assert "Heading 1" in styles and len(d.tables) == 1
    back = read_docx(io.BytesIO(buf.getvalue()))
    assert len(back.chapters) >= 4  # + «Notas» (las notas van al final en Word)
