"""Texto plano → ``Document``. Párrafos por línea en blanco; títulos por patrón."""

from __future__ import annotations

import re

from ..model import Heading, Paragraph, Rule, Text
from .markdown_reader import split_chapters

_CHAPTER = re.compile(
    r"^\s*((cap[ií]tulo|chapter|parte)\s+[\wáéíóú]+.*|pr[oó]logo.*|ep[ií]logo.*|interludio.*|"
    r"pre[aá]mbulo.*|introducci[oó]n|agradecimientos|ap[eé]ndice.*)\s*$", re.I)
_SCENE = re.compile(r"^\s*([*#~·•⁂]\s*){1,5}$")


def read_text(src: str) -> "Document":
    src = src.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    paras = re.split(r"\n\s*\n", src)
    # Textos con un párrafo por línea (sin líneas en blanco): cada línea es un párrafo.
    if len(paras) < 3 and src.count("\n") > 10:
        paras = src.split("\n")
    blocks = []
    for raw in paras:
        text = " ".join(l.strip() for l in raw.strip().split("\n"))
        if not text:
            continue
        if _SCENE.match(text):
            blocks.append(Rule())
        elif len(text) < 90 and _CHAPTER.match(text):
            blocks.append(Heading(1, [Text(text)]))
        else:
            blocks.append(Paragraph([Text(text)]))
    return split_chapters(blocks, {})
