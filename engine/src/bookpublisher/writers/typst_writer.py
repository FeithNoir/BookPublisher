"""``Document`` → fuente Typst.

El escritor no decide nada de estilo: emite llamadas a funciones del tema
(``th.chapter-opening``, ``th.callout``…) y deja que cada ``theme.typ`` dibuje.
Todo el texto del usuario se escapa, así que un manuscrito nunca puede
inyectar código Typst.
"""

from __future__ import annotations

import re

from ..model import (
    Block, Callout, Chapter, CodeBlock, CodeSpan, Document, Emph, FootnoteRef, Heading, Image,
    Inline, LineBreak, Link, ListBlock, PageBreak, Paragraph, Quote, Rule, SmallCaps, Span,
    Strike, Strong, Table, Text, inline_text, to_roman,
)

# Caracteres con significado en el modo de marcado de Typst.
_ESC = str.maketrans({c: "\\" + c for c in "\\#$*_`<>@[]~/"})
_LINE_START = re.compile(r"(^|\n)([ \t]*)([=+\-]|\d+\.)", re.M)


# Raya de diálogo (es): nunca separar la raya de la palabra que abre o cierra.
_DASH_OPEN = re.compile(r"—(?=[\w¿¡«“\"'(])")
_DASH_CLOSE = re.compile(r"(?<=[\w.,;:!?…»”\")])—")
WJ = "\u2060"


def esc(text: str) -> str:
    if "—" in text:
        text = _DASH_CLOSE.sub(WJ + "—", _DASH_OPEN.sub("—" + WJ, text))
    s = text.translate(_ESC)
    # Marcas que solo son especiales al inicio de línea (=, -, +, 1.)
    s = _LINE_START.sub(lambda m: m.group(1) + m.group(2) + "\\" + m.group(3), s)
    return s


def tstr(value: str) -> str:
    """Literal de cadena Typst."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


class TypstWriter:
    def __init__(self, doc: Document, theme_id: str):
        self.doc = doc
        self.theme_id = theme_id

    # ------------------------------------------------------------- inlines
    def inl(self, nodes: list[Inline]) -> str:
        out: list[str] = []
        for n in nodes:
            if isinstance(n, Text):
                # Saltos de línea dentro de un texto: espacio (Typst ya los trata así).
                out.append(esc(n.text.replace("\n", " ")))
            elif isinstance(n, Emph):
                out.append("#emph[" + self.inl(n.children) + "]")
            elif isinstance(n, Strong):
                out.append("#strong[" + self.inl(n.children) + "]")
            elif isinstance(n, Strike):
                out.append("#strike[" + self.inl(n.children) + "]")
            elif isinstance(n, SmallCaps):
                out.append("#smallcaps[" + self.inl(n.children) + "]")
            elif isinstance(n, CodeSpan):
                out.append("#raw(" + tstr(n.text) + ")")
            elif isinstance(n, Link):
                out.append("#link(" + tstr(n.url) + ")[" + self.inl(n.children) + "]")
            elif isinstance(n, Span):
                out.append("#th.span(" + tstr(n.cls) + ", [" + self.inl(n.children) + "])")
            elif isinstance(n, FootnoteRef):
                body = self.doc.footnotes.get(n.label)
                if body:
                    out.append("#footnote[" + self.blocks(body, inline_ctx=True).strip() + "]")
            elif isinstance(n, LineBreak):
                out.append("#linebreak()")
        return "".join(out)

    # -------------------------------------------------------------- blocks
    def blocks(self, blocks: list[Block], inline_ctx: bool = False, after_break: bool = False) -> str:
        # Tras un título, un separador o un elemento no textual el párrafo va sin sangría
        # (los temas con sangría usan «all: true» para sangrar también tras una capitular).
        out = []
        prev: Block | None = None
        for i, b in enumerate(blocks):
            src = self.block(b)
            flush = isinstance(b, Paragraph) and (
                (i == 0 and after_break) or isinstance(prev, (Heading, Rule, PageBreak, Image, Table, CodeBlock, Callout)))
            out.append(f"#bp-flush[{src}]" if flush and src else src)
            prev = b
        return "\n\n".join(out)

    def block(self, b: Block) -> str:
        if isinstance(b, Paragraph):
            return self.inl(b.children)
        if isinstance(b, Heading):
            lvl = max(2, min(b.level, 4))
            title = self.inl(b.children)
            mark = "#section-mark(" + str(lvl) + ", " + tstr(inline_text(b.children).strip()) + ")"
            return mark + "#heading(level: " + str(lvl) + ", outlined: false, bookmarked: false)[" + title + "]"
        if isinstance(b, ListBlock):
            items = []
            for it in b.items:
                items.append("[" + self._item(it.blocks) + "]")
            fn = "enum" if b.ordered else "list"
            start = f"start: {b.start}, " if b.ordered and b.start != 1 else ""
            tight = "tight: false, " if any(len(it.blocks) > 1 for it in b.items) else ""
            return f"#{fn}({start}{tight}" + ", ".join(items) + ")"
        if isinstance(b, Quote):
            return "#quote(block: true)[" + self.blocks(b.blocks) + "]"
        if isinstance(b, Callout):
            title = tstr(b.title) if b.title else "none"
            return f"#th.callout({tstr(b.kind)}, {title}, [" + self.blocks(b.blocks) + "])"
        if isinstance(b, CodeBlock):
            lang = f"lang: {tstr(b.lang)}, " if b.lang else ""
            return f"#th.code-block(raw(block: true, {lang}{tstr(b.text)}))"
        if isinstance(b, Table):
            header = "(" + "".join("[" + self.inl(c) + "]," for c in b.header) + ")"
            n = max(1, len(b.header))
            rows = []
            for r in b.rows:
                cells = list(r)[:n] + [[]] * max(0, n - len(r))
                rows.append("(" + "".join("[" + self.inl(c) + "]," for c in cells) + ")")
            aligns = "(" + "".join(tstr(a or "") + "," for a in (b.aligns or [""] * n)) + ")"
            return "#th.table-block(" + header + ", (" + ",".join(rows) + ("," if len(rows) == 1 else "") + "), " + aligns + ")"
        if isinstance(b, Image):
            cap = "[" + self.inl(b.caption) + "]" if b.caption else "none"
            return f"#th.figure-image({tstr(_asset_path(b.src))}, {cap})"
        if isinstance(b, Rule):
            return "#th.scene-break()"
        if isinstance(b, PageBreak):
            return "#pagebreak()"
        return ""

    def _item(self, blocks: list[Block]) -> str:
        # Un ítem que empieza en negrita («**Torneos.** texto») usa la entrada del tema.
        if blocks and isinstance(blocks[0], Paragraph) and blocks[0].children and isinstance(blocks[0].children[0], Strong):
            first = blocks[0]
            lead = "#th.lead[" + self.inl(first.children[0].children) + "]" + self.inl(first.children[1:])
            rest = self.blocks(blocks[1:])
            return lead + ("\n\n" + rest if rest else "")
        return self.blocks(blocks)

    # ----------------------------------------------------------- chapters
    def chapter_info(self, ch: Chapter) -> str:
        label = chapter_label(ch, self.doc.meta)
        title_nodes = ch.title
        fields = [
            f"label: {tstr(label) if label else 'none'}",
            f"title: {'[' + self.inl(title_nodes) + ']' if inline_text(title_nodes).strip() else 'none'}",
            f"plain: {tstr(inline_text(title_nodes).strip() or (label or ''))}",
            f"number: {ch.number if ch.number else 'none'}",
            f"appendix: {'true' if getattr(ch, 'appendix', False) else 'false'}",
        ]
        return "(" + ", ".join(fields) + ")"

    def chapter_body(self, ch: Chapter, drop: bool = True) -> str:
        parts = [f"#th.chapter-opening({self.chapter_info(ch)}, meta)"]
        blocks = list(ch.blocks)
        dropped = False
        if blocks and isinstance(blocks[0], Paragraph) and drop:
            parts.append(self._first_paragraph(blocks[0]))
            blocks = blocks[1:]
            dropped = True
        if blocks:
            parts.append(self.blocks(blocks, after_break=not dropped))
        return "\n\n".join(parts)

    def _first_paragraph(self, p: Paragraph) -> str:
        full = self.inl(p.children)
        first = p.children[0] if p.children else None
        if isinstance(first, Text):
            txt = first.text.lstrip()
            if txt and txt[0].isalpha():
                letter = txt[0]
                rest_nodes = [Text(txt[1:])] + p.children[1:]
                rest = self.inl(rest_nodes)
                return f"#th.first-paragraph([{full}], letter: {tstr(letter)}, rest: [{rest}], meta: meta)"
        return f"#th.first-paragraph([{full}], meta: meta)"

    def meta_literal(self, extra: dict | None = None) -> str:
        meta = dict(self.doc.meta)
        if extra:
            meta.update(extra)
        return typst_value(meta, rich_keys=RICH_META)


RICH_META = {"subtitle", "description", "toc_note", "dedication", "epigraph"}
_LABEL_RE = re.compile(r"^\s*(cap[ií]tulo|chapter|parte|libro)\s+([\wáéíóú]+)\s*$", re.I)


def chapter_label(ch: Chapter, meta: dict) -> str | None:
    if ch.kicker:
        return ch.kicker
    if ch.numbered and ch.number:
        style = str(meta.get("chapter_numbering", "roman"))
        word = str(meta.get("chapter_word", "Capítulo"))
        num = to_roman(ch.number) if style == "roman" else str(ch.number)
        return f"{word} {num}"
    return None


def toc_label(ch: Chapter, meta: dict) -> str:
    if ch.kicker:
        m = re.match(r"^\s*anexo\s+(\w+)", ch.kicker, re.I)
        if m:
            return m.group(1)
        m = _LABEL_RE.match(ch.kicker)
        if m:
            return m.group(2)
        return "—"
    if ch.numbered and ch.number:
        style = str(meta.get("chapter_numbering", "roman"))
        return to_roman(ch.number) if style == "roman" else str(ch.number)
    return "—"


def _asset_path(src: str) -> str:
    if src.startswith(("http://", "https://")):
        return src
    return "/assets/" + src.split("/")[-1]


def typst_value(v, rich_keys: set[str] = frozenset(), key: str | None = None) -> str:
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, dict):
        if not v:
            return "(:)"
        items = []
        for k, val in v.items():
            items.append(tstr(str(k)) + ": " + typst_value(val, rich_keys, str(k)))
        return "(" + ", ".join(items) + ")"
    if isinstance(v, (list, tuple)):
        return "(" + "".join(typst_value(x, rich_keys) + ", " for x in v) + ")"
    s = str(v)
    if key in rich_keys:
        from ..readers.markdown_reader import read_inline
        w = TypstWriter(Document(), "")
        return "[" + w.inl(read_inline(s)) + "]"
    return tstr(s)
