"""Ajustes previos al render que no cambian el texto del autor."""

from __future__ import annotations

import re

from ..model import Chapter, Document, Text, inline_text

_NUMBERED = re.compile(r"^\s*(cap[ií]tulo|chapter)\s+([\w]+)\s*(?:[:.\-—–]\s*(.+))?$", re.I)
_SPECIAL = re.compile(
    r"^\s*(pr[oó]logo|ep[ií]logo|interludio|pre[aá]mbulo|introducci[oó]n|colof[oó]n|ap[eé]ndice|"
    r"anexo\s+\w+|nota del autor|agradecimientos|dedicatoria)\s*(?:[:.\-—–]\s*(.+))?$", re.I)


def normalize_titles(doc: Document) -> Document:
    """«Capítulo 3: El puerto» → etiqueta «Capítulo 3» + título «El puerto».
    «Epílogo: …» → capítulo sin número con etiqueta «Epílogo».
    Solo actúa en títulos de texto plano y nunca inventa números."""
    for ch in doc.chapters:
        if ch.kicker or not ch.title or not all(isinstance(n, Text) for n in ch.title):
            continue
        text = inline_text(ch.title).strip()
        m = _NUMBERED.match(text)
        if m:
            ch.kicker = f"{m.group(1)} {m.group(2)}"
            ch.title = [Text(m.group(3).strip())] if m.group(3) else []
            continue
        m = _SPECIAL.match(text)
        if m:
            ch.numbered = False
            if m.group(2):
                ch.kicker = m.group(1)
                ch.title = [Text(m.group(2).strip())]
    doc.number_chapters()
    return doc


_DIALOGUE = re.compile(r"^([—―])[ \u00a0]+(?=\S)")


def fix_dialogue_dashes(doc: Document) -> int:
    """«— Hola» → «—Hola» al inicio de párrafo: en español la raya de diálogo va pegada.
    Muchos textos (p. ej. los de Proyecto Gutenberg) la separan con un espacio."""
    from ..model import Paragraph, Quote

    fixed = 0

    def walk(blocks):
        nonlocal fixed
        for b in blocks:
            if isinstance(b, Paragraph) and b.children and isinstance(b.children[0], Text):
                new = _DIALOGUE.sub(r"\1", b.children[0].text)
                if new != b.children[0].text:
                    b.children[0].text = new
                    fixed += 1
            elif isinstance(b, Quote):
                walk(b.blocks)

    walk(doc.front)
    for ch in doc.chapters:
        walk(ch.blocks)
    return fixed
