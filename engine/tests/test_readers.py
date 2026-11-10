from bookpublisher.model import Callout, CodeBlock, FootnoteRef, ListBlock, Paragraph, SmallCaps, Span, Table, inline_text
from bookpublisher.readers import read_any
from bookpublisher.readers.markdown_reader import read_markdown
from bookpublisher.readers.text_reader import read_text
from bookpublisher.render.normalize import fix_dialogue_dashes, normalize_titles


def walk(blocks):
    for b in blocks:
        yield b
        for attr in ("blocks", "items"):
            for x in getattr(b, attr, []) or []:
                yield from walk(x if isinstance(x, list) else getattr(x, "blocks", [x]))


def test_markdown_structure(samples):
    doc = read_any(samples / "guia-formato.md")
    assert doc.meta["title"] == "Guía del formato de BookPublisher"
    assert len(doc.chapters) == 4
    blocks = [b for ch in doc.chapters for b in walk(ch.blocks)]
    assert any(isinstance(b, Callout) and b.kind == "consejo" for b in blocks)
    assert any(isinstance(b, CodeBlock) for b in blocks)
    assert any(isinstance(b, Table) for b in blocks)
    assert any(isinstance(b, ListBlock) and b.ordered for b in blocks)
    assert len(doc.footnotes) == 2


def test_chapter_titles_normalized():
    doc = read_markdown("# Capítulo 3: El puerto\n\nTexto.\n\n# Epílogo: Después\n\nFin.\n")
    normalize_titles(doc)
    doc.number_chapters()
    a, b = doc.chapters
    assert a.kicker == "Capítulo 3" and inline_text(a.title) == "El puerto"
    assert not b.numbered and b.kicker.lower().startswith("epílogo")


def test_lone_first_line_is_title():
    doc = read_markdown("Mi libro\n\n# Uno\n\nHola.\n")
    assert doc.meta["title"] == "Mi libro"


def test_pendiente_and_smallcaps_spans():
    doc = read_markdown("# A\n\n*Pendiente de consultar: la fecha.* y [Sakura Fest]{.smallcaps}.\n")
    p = doc.chapters[0].blocks[0]
    assert isinstance(p.children[0], Span) and p.children[0].cls == "pendiente"
    assert any(isinstance(n, SmallCaps) for n in p.children)


def test_dialogue_dash_fix():
    doc = read_markdown("# A\n\n— Hola —dijo.\n\n—Bien.\n")
    assert fix_dialogue_dashes(doc) == 1
    assert inline_text(doc.chapters[0].blocks[0].children).startswith("—Hola")


def test_plain_text_chapters():
    doc = read_text("Capítulo 1\n\nUno.\n\nCapítulo 2\n\nDos.\n")
    assert len(doc.chapters) == 2


def test_footnote_refs(samples):
    doc = read_any(samples / "guia-formato.md")
    refs = [n for ch in doc.chapters for b in walk(ch.blocks) if isinstance(b, Paragraph)
            for n in b.children if isinstance(n, FootnoteRef)]
    assert len(refs) == 2
