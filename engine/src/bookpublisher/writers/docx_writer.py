"""``Document`` → Word (.docx) con estilos nativos de Word.

Títulos con «Título 1…4» (Heading), listas con «List Bullet/Number», tablas con
«Table Grid», imágenes incrustadas, cursivas/negritas/versalitas, la cruz † y
«Pendiente de consultar» en rojo. python-docx no escribe notas al pie reales:
las notas van numeradas al final, en una sección «Notas».
"""

from __future__ import annotations

import io

from docx import Document as Docx
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from ..model import (
    Block, Callout, CodeBlock, CodeSpan, Document, Emph, FootnoteRef, Heading, Image, Inline,
    LineBreak, Link, ListBlock, PageBreak, Paragraph, Quote, Rule, SmallCaps, Span, Strike, Strong,
    Table, Text, inline_text,
)
from .typst_writer import chapter_label

RED = RGBColor(0x8C, 0x2F, 0x1B)
CALLOUT_TITLES = {"nota": "Nota", "consejo": "Consejo", "importante": "Importante", "advertencia": "Advertencia",
                  "aviso": "Aviso", "precaucion": "Precaución"}


class _Ctx:
    def __init__(self, doc: Document):
        self.doc = doc
        self.notes: list[str] = []


def _word_safe(data: bytes) -> bytes:
    """python-docx no reconoce algunos JPEG sin cabecera JFIF/EXIF (habituales en PDF):
    si no los entiende, se recodifican a PNG con Pillow."""
    from docx.image.image import Image as DocxImage

    try:
        DocxImage.from_blob(data)
        return data
    except Exception:  # noqa: BLE001
        from PIL import Image as PILImage
        out = io.BytesIO()
        PILImage.open(io.BytesIO(data)).save(out, format="PNG")
        return out.getvalue()


def _shade(paragraph_or_cell, hex_fill: str) -> None:
    el = paragraph_or_cell._p if hasattr(paragraph_or_cell, "_p") else paragraph_or_cell._tc
    pr = el.get_or_add_pPr() if hasattr(el, "get_or_add_pPr") else el.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    pr.append(shd)


def _border(paragraph, color: str = "8C2F1B", side: str = "left") -> None:
    pPr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), "12")
    el.set(qn("w:space"), "8")
    el.set(qn("w:color"), color)
    bdr.append(el)
    pPr.append(bdr)


def _runs(par, nodes: list[Inline], ctx: _Ctx, fmt: dict | None = None) -> None:
    fmt = fmt or {}
    for n in nodes:
        if isinstance(n, Text):
            _add_text(par, n.text, fmt)
        elif isinstance(n, Emph):
            _runs(par, n.children, ctx, {**fmt, "italic": True})
        elif isinstance(n, Strong):
            _runs(par, n.children, ctx, {**fmt, "bold": True})
        elif isinstance(n, Strike):
            _runs(par, n.children, ctx, {**fmt, "strike": True})
        elif isinstance(n, SmallCaps):
            _runs(par, n.children, ctx, {**fmt, "smallcaps": True})
        elif isinstance(n, CodeSpan):
            _add_text(par, n.text, {**fmt, "mono": True})
        elif isinstance(n, Link):
            _runs(par, n.children, ctx, {**fmt, "underline": True})
            if n.url and n.url != inline_text(n.children):
                _add_text(par, f" ({n.url})", {**fmt, "size": 9})
        elif isinstance(n, Span):
            extra = {"red": True}
            if n.cls == "pendiente":
                extra.update(italic=True, underline="dotted")
            _runs(par, n.children, ctx, {**fmt, **extra})
        elif isinstance(n, FootnoteRef):
            body = ctx.doc.footnotes.get(n.label)
            if body:
                ctx.notes.append(" ".join(inline_text(b.children) for b in body if isinstance(b, Paragraph)))
                _add_text(par, str(len(ctx.notes)), {**fmt, "sup": True})
        elif isinstance(n, LineBreak):
            par.add_run().add_break()


def _add_text(par, text: str, fmt: dict) -> None:
    # La cruz † va siempre en rojo, como en el códice.
    pieces = text.split("†")
    for i, piece in enumerate(pieces):
        if i:
            r = par.add_run("†")
            _apply(r, {**fmt, "red": True})
        if piece:
            _apply(par.add_run(piece), fmt)


def _apply(run, fmt: dict) -> None:
    f = run.font
    if fmt.get("bold"):
        f.bold = True
    if fmt.get("italic"):
        f.italic = True
    if fmt.get("strike"):
        f.strike = True
    if fmt.get("smallcaps"):
        f.small_caps = True
    if fmt.get("sup"):
        f.superscript = True
    if fmt.get("red"):
        f.color.rgb = RED
    if fmt.get("mono"):
        f.name = "Consolas"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
    if fmt.get("size"):
        f.size = Pt(fmt["size"])
    u = fmt.get("underline")
    if u == "dotted":
        rPr = run._element.get_or_add_rPr()
        el = OxmlElement("w:u")
        el.set(qn("w:val"), "dotted")
        rPr.append(el)
    elif u:
        f.underline = True


def _blocks(d, blocks: list[Block], ctx: _Ctx, list_level: int = 0) -> None:
    for b in blocks:
        _block(d, b, ctx, list_level)


def _block(d, b: Block, ctx: _Ctx, list_level: int = 0) -> None:
    if isinstance(b, Paragraph):
        _runs(d.add_paragraph(), b.children, ctx)
    elif isinstance(b, Heading):
        h = d.add_heading(level=min(max(b.level, 2), 4))
        _runs(h, b.children, ctx)
    elif isinstance(b, ListBlock):
        style = "List Number" if b.ordered else "List Bullet"
        if list_level:
            style += f" {min(list_level + 1, 3)}"
        for it in b.items:
            first = True
            for ib in it.blocks:
                if isinstance(ib, Paragraph) and first:
                    p = d.add_paragraph(style=style)
                    _runs(p, ib.children, ctx)
                elif isinstance(ib, ListBlock):
                    _block(d, ib, ctx, list_level + 1)
                else:
                    _block(d, ib, ctx, list_level)
                first = False
    elif isinstance(b, Quote):
        for ib in b.blocks:
            if isinstance(ib, Paragraph):
                p = d.add_paragraph(style="Quote")
                _runs(p, ib.children, ctx)
            else:
                _block(d, ib, ctx)
    elif isinstance(b, Callout):
        title = b.title or CALLOUT_TITLES.get(b.kind, "Nota")
        p = d.add_paragraph()
        _shade(p, "F3ECDD")
        _border(p)
        r = p.add_run(title + " ")
        r.font.bold = True
        r.font.small_caps = True
        for i, ib in enumerate(b.blocks):
            if isinstance(ib, Paragraph):
                if i:
                    p = d.add_paragraph()
                    _shade(p, "F3ECDD")
                    _border(p)
                _runs(p, ib.children, ctx)
            else:
                _block(d, ib, ctx)
    elif isinstance(b, CodeBlock):
        for line in b.text.split("\n") or [""]:
            p = d.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            _shade(p, "F2F2F2")
            _add_text(p, line or " ", {"mono": True, "size": 9})
    elif isinstance(b, Table):
        n = max(len(b.header), max((len(r) for r in b.rows), default=0), 1)
        t = d.add_table(rows=1 + len(b.rows), cols=n)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i in range(n):
            cell = t.rows[0].cells[i]
            _shade(cell, "E3D5B8")
            par = cell.paragraphs[0]
            _runs(par, b.header[i] if i < len(b.header) else [], ctx, {"bold": True})
        for ri, row in enumerate(b.rows, start=1):
            for ci in range(n):
                par = t.rows[ri].cells[ci].paragraphs[0]
                if ci < len(row):
                    _runs(par, row[ci], ctx)
                al = b.aligns[ci] if ci < len(b.aligns) else ""
                if al == "center":
                    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif al == "right":
                    par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        d.add_paragraph()
    elif isinstance(b, Image):
        data = ctx.doc.assets.get(b.src)
        if data:
            try:
                d.add_picture(io.BytesIO(_word_safe(data)), width=Cm(12))
                d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except Exception:  # noqa: BLE001
                d.add_paragraph(f"[Imagen: {b.src}]")
        else:
            d.add_paragraph(f"[Imagen: {b.src}]")
        if b.caption:
            p = d.add_paragraph(style="Caption")
            _runs(p, b.caption, ctx)
    elif isinstance(b, Rule):
        p = d.add_paragraph("⁂")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif isinstance(b, PageBreak):
        d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def write_docx(doc: Document, out) -> None:
    """Escribe el documento en ``out`` (ruta o archivo binario)."""
    d = Docx()
    ctx = _Ctx(doc)
    styles = d.styles
    normal = styles["Normal"]
    normal.font.name = "Georgia"
    normal.font.size = Pt(11)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Georgia")
    lang = str(doc.meta.get("lang", "es-ES"))
    for st in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Title"):
        rpr = styles[st].element.get_or_add_rPr()
        el = OxmlElement("w:lang")
        el.set(qn("w:val"), lang if "-" in lang else "es-ES")
        rpr.append(el)
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(2.5))

    core = d.core_properties
    core.title = doc.title
    core.author = str(doc.meta.get("author", "") or "")
    core.comments = "Generado con BookPublisher"

    # Portada
    m = doc.meta
    if m.get("kicker"):
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _apply(p.add_run(str(m["kicker"])), {"size": 9, "smallcaps": True})
    if m.get("cover_image") and m["cover_image"] in doc.assets:
        try:
            d.add_picture(io.BytesIO(_word_safe(doc.assets[m["cover_image"]])), height=Cm(5))
            d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            pass
    t = d.add_paragraph(doc.title, style="Title")
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for key in ("subtitle", "author", "description", "place", "edition"):
        if m.get(key):
            p = d.add_paragraph(style="Subtitle" if key == "subtitle" else None)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            from ..readers.markdown_reader import read_inline
            _runs(p, read_inline(str(m[key])), ctx, {"italic": key in ("description",)})
    if m.get("toc_note"):
        from ..readers.markdown_reader import read_inline
        p = d.add_paragraph()
        _shade(p, "F3ECDD")
        _border(p)
        r = p.add_run(str(m.get("toc_note_title", "Aviso al lector.")) + " ")
        r.font.small_caps = True
        _runs(p, read_inline(str(m["toc_note"])), ctx)
    if doc.front:
        _blocks(d, doc.front, ctx)

    for i, ch in enumerate(doc.chapters):
        d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        label = chapter_label(ch, doc.meta)
        if label:
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _apply(p.add_run(label.upper()), {"red": True, "size": 9})
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.keep_with_next = True
        h = d.add_heading(level=1)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _runs(h, ch.title or [Text(label or "")], ctx)
        _blocks(d, ch.blocks, ctx)

    if ctx.notes:
        d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        d.add_heading("Notas", level=1)
        for i, note in enumerate(ctx.notes, start=1):
            p = d.add_paragraph()
            _apply(p.add_run(f"{i}. "), {"bold": True})
            _add_text(p, note, {})
    d.save(out)
