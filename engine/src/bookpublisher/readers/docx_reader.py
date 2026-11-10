"""Word (.docx) → ``Document`` para exportarlo con un tema."""

from __future__ import annotations

import re

from docx import Document as Docx
from docx.oxml.ns import qn

from ..model import Emph, Heading, Image, Inline, ListBlock, ListItem, Paragraph, Strong, Table, Text
from .markdown_reader import _mark_pendientes, split_chapters

_HEADING = re.compile(r"^(heading|t[ií]tulo|encabezado)\s*(\d)$", re.I)


def _inlines(par) -> list[Inline]:
    out: list[Inline] = []
    for run in par.runs:
        t = run.text
        if not t:
            continue
        node: Inline = Text(t)
        if run.italic:
            node = Emph([node])
        if run.bold:
            node = Strong([node])
        if out and type(out[-1]) is type(node) and not isinstance(node, Text):
            out[-1].children.extend(node.children)  # type: ignore[union-attr]
        elif out and isinstance(out[-1], Text) and isinstance(node, Text):
            out[-1] = Text(out[-1].text + node.text)
        else:
            out.append(node)
    return _mark_pendientes(out)


def read_docx(path_or_file) -> "Document":
    d = Docx(path_or_file)
    meta: dict = {}
    if d.core_properties.title:
        meta["title"] = d.core_properties.title
    if d.core_properties.author:
        meta["author"] = d.core_properties.author
    blocks = []
    body = d.element.body
    paras = {p._p: p for p in d.paragraphs}
    tables = {t._tbl: t for t in d.tables}
    assets: dict[str, bytes] = {}
    for el in body.iterchildren():
        if el.tag == qn("w:p") and el in paras:
            p = paras[el]
            style = (p.style.name if p.style is not None else "") or ""
            text = p.text.strip()
            blips = el.findall(".//" + qn("a:blip"))
            for blip in blips:
                rid = blip.get(qn("r:embed"))
                part = d.part.related_parts.get(rid) if rid else None
                if part is not None:
                    name = f"docx-{len(assets) + 1}{'.' + part.partname.ext if hasattr(part.partname, 'ext') else '.png'}"
                    assets[name] = part.blob
                    blocks.append(Image(name))
            if not text:
                continue
            m = _HEADING.match(style)
            if style.lower() in ("title", "título") and "title" not in meta:
                meta["title"] = text
            elif style.lower() in ("subtitle", "subtítulo"):
                meta["subtitle"] = text
            elif m:
                blocks.append(Heading(int(m.group(2)), _inlines(p)))
            elif el.find(".//" + qn("w:numPr")) is not None or style.lower().startswith(("list", "lista")):
                ordered = "number" in style.lower() or "núm" in style.lower()
                item = ListItem([Paragraph(_inlines(p))])
                if blocks and isinstance(blocks[-1], ListBlock) and blocks[-1].ordered == ordered:
                    blocks[-1].items.append(item)
                else:
                    blocks.append(ListBlock(ordered, [item]))
            else:
                blocks.append(Paragraph(_inlines(p)))
        elif el.tag == qn("w:tbl") and el in tables:
            t = tables[el]
            rows = [[[Text(c.text.strip())] for c in r.cells] for r in t.rows]
            if rows:
                blocks.append(Table(rows[0], rows[1:], [""] * len(rows[0])))
    doc = split_chapters(blocks, meta)
    doc.assets = assets
    return doc
