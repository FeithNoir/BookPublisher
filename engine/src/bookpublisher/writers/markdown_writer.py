"""``Document`` → Markdown (el dialecto que lee ``markdown_reader``)."""

from __future__ import annotations

import re

import yaml

from ..model import (
    Block, Callout, Chapter, CodeBlock, CodeSpan, Document, Emph, FootnoteRef, Heading, Image,
    Inline, LineBreak, Link, ListBlock, PageBreak, Paragraph, Quote, Rule, SmallCaps, Span,
    Strike, Strong, Table, Text,
)

_MD_ESC = re.compile(r"([\\`*_\[\]<>|])")
_LINE_START = re.compile(r"^(\s*)([#>+\-]|\d+[.)])(?=\s)", re.M)

KIND_TO_ALERT = {"nota": "NOTE", "consejo": "TIP", "importante": "IMPORTANT", "advertencia": "WARNING",
                 "aviso": "AVISO", "precaucion": "CAUTION"}
META_ORDER = ["title", "subtitle", "author", "kicker", "description", "place", "edition", "colophon_line",
              "header", "cover_image", "toc_kicker", "toc_title", "toc_note_title", "toc_note", "lang"]


def esc_md(text: str) -> str:
    s = _MD_ESC.sub(r"\\\1", text)
    return _LINE_START.sub(lambda m: m.group(1) + "\\" + m.group(2), s)


def inl(nodes: list[Inline]) -> str:
    out = []
    for n in nodes:
        if isinstance(n, Text):
            out.append(esc_md(n.text))
        elif isinstance(n, Emph):
            out.append("*" + inl(n.children) + "*")
        elif isinstance(n, Strong):
            out.append("**" + inl(n.children) + "**")
        elif isinstance(n, Strike):
            out.append("~~" + inl(n.children) + "~~")
        elif isinstance(n, SmallCaps):
            out.append("[" + inl(n.children) + "]{.smallcaps}")
        elif isinstance(n, CodeSpan):
            fence = "``" if "`" in n.text else "`"
            out.append(fence + n.text + fence)
        elif isinstance(n, Link):
            out.append("[" + inl(n.children) + "](" + n.url + ")")
        elif isinstance(n, Span):
            out.append("[" + inl(n.children) + "]{." + n.cls + "}")
        elif isinstance(n, FootnoteRef):
            out.append("[^" + n.label + "]")
        elif isinstance(n, LineBreak):
            out.append("\\\n")
    return "".join(out)


def _indent(text: str, prefix: str) -> str:
    return "\n".join((prefix + l) if l else prefix.rstrip() for l in text.split("\n"))


def block(b: Block) -> str:
    if isinstance(b, Paragraph):
        return inl(b.children)
    if isinstance(b, Heading):
        attrs = []
        if not b.numbered:
            attrs.append(".unnumbered")
        if b.kicker:
            attrs.append(f'kicker="{b.kicker}"')
        suffix = " {" + " ".join(attrs) + "}" if attrs else ""
        return "#" * b.level + " " + inl(b.children) + suffix
    if isinstance(b, ListBlock):
        lines = []
        for i, it in enumerate(b.items):
            marker = f"{b.start + i}." if b.ordered else "-"
            body = blocks(it.blocks)
            pad = " " * (len(marker) + 1)
            first, *rest = body.split("\n")
            lines.append(marker + " " + first + ("\n" + _indent("\n".join(rest), pad) if rest else ""))
        sep = "\n\n" if any(len(it.blocks) > 1 for it in b.items) else "\n"
        return sep.join(lines)
    if isinstance(b, Quote):
        return _indent(blocks(b.blocks), "> ")
    if isinstance(b, Callout):
        head = f"> [!{KIND_TO_ALERT.get(b.kind, 'NOTE')}]" + (f" {b.title}" if b.title else "")
        return head + "\n" + _indent(blocks(b.blocks), "> ")
    if isinstance(b, CodeBlock):
        fence = "````" if "```" in b.text else "```"
        return f"{fence}{b.lang}\n{b.text}\n{fence}"
    if isinstance(b, Table):
        n = max(len(b.header), max((len(r) for r in b.rows), default=0))
        def row(cells):
            cells = list(cells) + [[]] * (n - len(cells))
            return "| " + " | ".join(inl(c).replace("\n", " ") for c in cells) + " |"
        al = []
        for i in range(n):
            a = b.aligns[i] if i < len(b.aligns) else ""
            al.append({"center": ":-:", "right": "--:", "left": ":--"}.get(a, "---"))
        return "\n".join([row(b.header), "| " + " | ".join(al) + " |"] + [row(r) for r in b.rows])
    if isinstance(b, Image):
        cap = inl(b.caption)
        return f"![{esc_md(b.alt) or cap}]({b.src})"
    if isinstance(b, Rule):
        return "* * *"
    if isinstance(b, PageBreak):
        return "<!-- pagebreak -->"
    return ""


def blocks(bs: list[Block]) -> str:
    return "\n\n".join(x for x in (block(b) for b in bs) if x != "")


def write_markdown(doc: Document, *, chapter_level: int = 1) -> str:
    parts = []
    meta = {k: doc.meta[k] for k in META_ORDER if doc.meta.get(k) not in (None, "")}
    for k, v in doc.meta.items():
        if k not in meta and v not in (None, "") and k != "options":
            meta[k] = v
    if meta:
        parts.append("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=100).strip() + "\n---")
    if doc.front:
        parts.append(blocks(doc.front))
    for ch in doc.chapters:
        h = Heading(chapter_level, ch.title, kicker=ch.kicker, numbered=ch.numbered)
        parts.append(block(h))
        if ch.blocks:
            parts.append(blocks(_shift(ch.blocks, chapter_level - 1)))
    if doc.footnotes:
        notes = []
        for label, body in doc.footnotes.items():
            text = blocks(body)
            first, *rest = text.split("\n")
            notes.append(f"[^{label}]: {first}" + ("\n" + _indent("\n".join(rest), "    ") if rest else ""))
        parts.append("\n".join(notes))
    return "\n\n".join(parts).rstrip() + "\n"


def _shift(bs: list[Block], by: int) -> list[Block]:
    if by == 0:
        return bs
    out = []
    for b in bs:
        if isinstance(b, Heading):
            b = Heading(min(6, b.level + by), b.children, b.kicker, b.numbered)
        out.append(b)
    return out
