"""Modelo de documento común a lectores y escritores.

Todo lo que entra (Markdown, texto plano, DOCX, PDF) se convierte en un
``Document``; todo lo que sale (Markdown, DOCX, Typst→PDF) se escribe desde él.
Los nodos son dataclasses pequeñas y sin lógica para que sean fáciles de
serializar, comparar en pruebas y enviar a los procesos de render.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Union

# ---------------------------------------------------------------- inlines


@dataclass
class Text:
    text: str


@dataclass
class Emph:
    children: list["Inline"]


@dataclass
class Strong:
    children: list["Inline"]


@dataclass
class Strike:
    children: list["Inline"]


@dataclass
class SmallCaps:
    children: list["Inline"]


@dataclass
class CodeSpan:
    text: str


@dataclass
class Link:
    url: str
    children: list["Inline"]


@dataclass
class Span:
    """Texto con una clase semántica, p. ej. ``pendiente`` o ``propuesta``."""

    cls: str
    children: list["Inline"]


@dataclass
class FootnoteRef:
    label: str


@dataclass
class LineBreak:
    pass


Inline = Union[Text, Emph, Strong, Strike, SmallCaps, CodeSpan, Link, Span, FootnoteRef, LineBreak]

# ----------------------------------------------------------------- blocks


@dataclass
class Heading:
    level: int
    children: list[Inline]
    kicker: str | None = None  # p. ej. "Preámbulo", "Anexo A"
    numbered: bool = True


@dataclass
class Paragraph:
    children: list[Inline]


@dataclass
class ListItem:
    blocks: list["Block"]


@dataclass
class ListBlock:
    ordered: bool
    items: list[ListItem]
    start: int = 1


@dataclass
class Quote:
    blocks: list["Block"]


@dataclass
class Callout:
    """Recuadro: nota, consejo, aviso, importante, precaución."""

    kind: str
    title: str | None
    blocks: list["Block"]


@dataclass
class CodeBlock:
    text: str
    lang: str = ""


@dataclass
class Table:
    header: list[list[Inline]]
    rows: list[list[list[Inline]]]
    aligns: list[str] = field(default_factory=list)  # "left" | "center" | "right" | ""


@dataclass
class Image:
    src: str
    alt: str = ""
    caption: list[Inline] = field(default_factory=list)


@dataclass
class Rule:
    """Separador de escena o de sección (``***``)."""


@dataclass
class PageBreak:
    pass


Block = Union[Heading, Paragraph, ListBlock, Quote, Callout, CodeBlock, Table, Image, Rule, PageBreak]

# --------------------------------------------------------------- document


@dataclass
class Chapter:
    title: list[Inline]
    blocks: list[Block]
    kicker: str | None = None
    numbered: bool = True
    # Número que el tema mostrará ("I", "1"…); lo asigna ``number_chapters``.
    number: int | None = None

    def fingerprint(self, footnotes: dict[str, list[Block]] | None = None) -> str:
        payload = {"t": _plain(self), "f": footnotes or {}}
        raw = json.dumps(payload, default=_jsonable, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass
class Document:
    meta: dict = field(default_factory=dict)
    front: list[Block] = field(default_factory=list)  # bloques antes del primer capítulo
    chapters: list[Chapter] = field(default_factory=list)
    footnotes: dict[str, list[Block]] = field(default_factory=dict)
    # Archivos binarios (imágenes) referenciados por ``Image.src``.
    assets: dict[str, bytes] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or "Sin título")

    def number_chapters(self) -> None:
        n = 0
        for ch in self.chapters:
            if ch.numbered:
                n += 1
                ch.number = n
            else:
                ch.number = None


def _jsonable(obj):
    if hasattr(obj, "__dataclass_fields__"):
        d = asdict(obj)
        d["_k"] = type(obj).__name__
        return d
    raise TypeError(type(obj))


def _plain(obj):
    return json.loads(json.dumps(obj, default=_jsonable, ensure_ascii=False))


# ---------------------------------------------------------------- helpers


def inline_text(nodes: list[Inline]) -> str:
    """Texto plano de una lista de inlines (para índices, marcadores y conteos)."""
    out: list[str] = []
    for n in nodes:
        if isinstance(n, Text):
            out.append(n.text)
        elif isinstance(n, CodeSpan):
            out.append(n.text)
        elif isinstance(n, LineBreak):
            out.append(" ")
        elif isinstance(n, FootnoteRef):
            continue
        else:
            out.append(inline_text(n.children))
    return "".join(out)


def block_words(blocks: list[Block]) -> int:
    total = 0
    for b in blocks:
        if isinstance(b, (Paragraph, Heading)):
            total += len(inline_text(b.children).split())
        elif isinstance(b, ListBlock):
            for it in b.items:
                total += block_words(it.blocks)
        elif isinstance(b, (Quote, Callout)):
            total += block_words(b.blocks)
        elif isinstance(b, CodeBlock):
            total += len(b.text.split())
        elif isinstance(b, Table):
            for row in [b.header, *b.rows]:
                for cell in row:
                    total += len(inline_text(cell).split())
    return total


def chapter_words(ch: Chapter) -> int:
    return len(inline_text(ch.title).split()) + block_words(ch.blocks)


def footnote_labels(blocks: list[Block]) -> list[str]:
    """Etiquetas de notas al pie usadas en estos bloques, en orden."""
    found: list[str] = []

    def walk_inl(nodes):
        for n in nodes:
            if isinstance(n, FootnoteRef):
                if n.label not in found:
                    found.append(n.label)
            elif hasattr(n, "children") and isinstance(getattr(n, "children"), list):
                walk_inl(n.children)

    def walk(bs):
        for b in bs:
            if isinstance(b, (Paragraph, Heading)):
                walk_inl(b.children)
            elif isinstance(b, ListBlock):
                for it in b.items:
                    walk(it.blocks)
            elif isinstance(b, (Quote, Callout)):
                walk(b.blocks)
            elif isinstance(b, Table):
                for row in [b.header, *b.rows]:
                    for c in row:
                        walk_inl(c)
            elif isinstance(b, Image):
                walk_inl(b.caption)

    walk(blocks)
    return found


ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
         (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n: int) -> str:
    out = []
    for v, s in ROMAN:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)
