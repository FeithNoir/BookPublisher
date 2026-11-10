"""Markdown → ``Document``.

Dialecto: CommonMark + tablas GFM + tachado + notas al pie (``[^1]``) +
front matter YAML + spans con clase (``[texto]{.pendiente}``) + alertas al
estilo GitHub en citas (``> [!NOTE]``, ``> [!AVISO] Título``).
Los encabezados aceptan atributos al final: ``# Anexo A {.unnumbered kicker="Anexo A"}``.
"""

from __future__ import annotations

import re

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.attrs import attrs_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

from ..model import (
    Block, Callout, Chapter, CodeBlock, CodeSpan, Document, Emph, FootnoteRef, Heading, Image,
    Inline, LineBreak, Link, ListBlock, ListItem, PageBreak, Paragraph, Quote, Rule, SmallCaps,
    Span, Strike, Strong, Table, Text, inline_text,
)

CALLOUT_KINDS = {
    "NOTE": "nota", "NOTA": "nota",
    "TIP": "consejo", "CONSEJO": "consejo",
    "IMPORTANT": "importante", "IMPORTANTE": "importante",
    "WARNING": "advertencia", "ADVERTENCIA": "advertencia", "AVISO": "aviso",
    "CAUTION": "precaucion", "PRECAUCION": "precaucion", "PRECAUCIÓN": "precaucion",
}
_CALLOUT_RE = re.compile(r"^\[!([A-Za-zÁÉÍÓÚáéíóú]+)\][ \t]*(.*)$")
_ATTR_RE = re.compile(r"\s*\{([^{}]*)\}\s*$")
_KV_RE = re.compile(r'([\w-]+)=(?:"([^"]*)"|(\S+))')
PENDIENTE_RE = re.compile(r"^\s*pendiente de consultar", re.IGNORECASE)


def _md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"typographer": False}).enable(["table", "strikethrough"])
    md.use(front_matter_plugin).use(footnote_plugin).use(attrs_plugin, spans=True)
    return md


def parse_attrs(raw: str) -> dict:
    out: dict = {"classes": []}
    for m in _KV_RE.finditer(raw):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    rest = _KV_RE.sub("", raw)
    for tok in rest.split():
        if tok.startswith("."):
            out["classes"].append(tok[1:])
        elif tok == "-":
            out["classes"].append("unnumbered")
    return out


class _Inlines:
    """Convierte tokens inline de markdown-it en nodos ``Inline``."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens or []
        self.i = 0

    def parse(self, stop: str | None = None) -> list[Inline]:
        out: list[Inline] = []
        while self.i < len(self.tokens):
            t = self.tokens[self.i]
            self.i += 1
            ty = t.type
            if stop and ty == stop:
                return out
            if ty == "text":
                _push_text(out, t.content)
            elif ty == "softbreak":
                _push_text(out, " ")
            elif ty == "hardbreak":
                out.append(LineBreak())
            elif ty == "code_inline":
                out.append(CodeSpan(t.content))
            elif ty == "em_open":
                out.append(Emph(self.parse("em_close")))
            elif ty == "strong_open":
                out.append(Strong(self.parse("strong_close")))
            elif ty == "s_open":
                out.append(Strike(self.parse("s_close")))
            elif ty == "link_open":
                out.append(Link(str(t.attrs.get("href", "")), self.parse("link_close")))
            elif ty == "span_open":
                cls = str(t.attrs.get("class", "")).split()
                kids = self.parse("span_close")
                if "smallcaps" in cls or "sc" in cls:
                    out.append(SmallCaps(kids))
                elif cls:
                    out.append(Span(cls[0], kids))
                else:
                    out.extend(kids)
            elif ty == "footnote_ref":
                out.append(FootnoteRef(str(t.meta.get("label", t.meta.get("id")))))
            elif ty == "image":
                # imagen dentro de párrafo: la tratamos como texto alternativo
                _push_text(out, t.content or "")
            elif ty in ("html_inline",):
                tag = t.content.lower()
                if tag in ("<br>", "<br/>", "<br />"):
                    out.append(LineBreak())
            # Otros tokens (cierres huérfanos) se ignoran.
        return [n for n in out if not (isinstance(n, Text) and n.text == "")]


def _push_text(out: list[Inline], s: str) -> None:
    if out and isinstance(out[-1], Text):
        out[-1] = Text(out[-1].text + s)
    else:
        out.append(Text(s))


def _strip_heading_attrs(nodes: list[Inline]) -> tuple[list[Inline], dict]:
    if nodes and isinstance(nodes[-1], Text):
        m = _ATTR_RE.search(nodes[-1].text)
        if m:
            nodes = nodes[:-1] + ([Text(nodes[-1].text[: m.start()])] if m.start() else [])
            return nodes, parse_attrs(m.group(1))
    return nodes, {"classes": []}


def _mark_pendientes(nodes: list[Inline]) -> list[Inline]:
    """Las cursivas que empiezan por «Pendiente de consultar» se marcan en rojo."""
    out = []
    for n in nodes:
        if isinstance(n, Emph) and PENDIENTE_RE.match(inline_text(n.children)):
            out.append(Span("pendiente", n.children))
        else:
            out.append(n)
    return out


class _Blocks:
    def __init__(self, tokens: list[Token], footnotes: dict):
        self.t = tokens
        self.i = 0
        self.footnotes = footnotes

    def parse(self, stop: str | None = None) -> list[Block]:
        out: list[Block] = []
        while self.i < len(self.t):
            tok = self.t[self.i]
            self.i += 1
            ty = tok.type
            if stop and ty == stop:
                return out
            if ty == "heading_open":
                inl = self._inline()
                self.i += 1  # heading_close
                nodes, attrs = _strip_heading_attrs(_Inlines(inl).parse())
                out.append(Heading(int(tok.tag[1]), nodes, kicker=attrs.get("kicker"),
                                   numbered="unnumbered" not in attrs["classes"]))
            elif ty == "paragraph_open":
                inl = self._inline()
                self.i += 1
                img = self._lone_image(inl)
                if img is not None:
                    out.append(img)
                else:
                    nodes = _Inlines(inl).parse()
                    if nodes:
                        out.append(Paragraph(_mark_pendientes(nodes)))
            elif ty in ("bullet_list_open", "ordered_list_open"):
                ordered = ty == "ordered_list_open"
                start = int(tok.attrs.get("start", 1)) if ordered else 1
                items: list[ListItem] = []
                close = ty.replace("open", "close")
                while self.i < len(self.t) and self.t[self.i].type != close:
                    if self.t[self.i].type == "list_item_open":
                        self.i += 1
                        items.append(ListItem(self.parse("list_item_close")))
                    else:
                        self.i += 1
                self.i += 1
                out.append(ListBlock(ordered, items, start))
            elif ty == "blockquote_open":
                inner = self.parse("blockquote_close")
                out.append(_quote_or_callout(inner))
            elif ty in ("fence", "code_block"):
                lang = (tok.info or "").strip().split(" ")[0]
                out.append(CodeBlock(tok.content.rstrip("\n"), lang))
            elif ty == "hr":
                out.append(Rule())
            elif ty == "table_open":
                out.append(self._table())
            elif ty == "html_block":
                if "pagebreak" in tok.content or "page-break" in tok.content:
                    out.append(PageBreak())
            elif ty == "footnote_block_open":
                self._footnotes()
        return out

    def _inline(self) -> list[Token]:
        tok = self.t[self.i]
        self.i += 1
        return tok.children or []

    @staticmethod
    def _lone_image(inl: list[Token]) -> Image | None:
        real = [t for t in inl if not (t.type == "text" and not t.content.strip()) and t.type != "softbreak"]
        if len(real) == 1 and real[0].type == "image":
            t = real[0]
            alt = "".join(c.content for c in (t.children or []))
            title = str(t.attrs.get("title", "") or "")
            cap = [Text(title)] if title else ([Text(alt)] if alt else [])
            return Image(str(t.attrs.get("src", "")), alt, cap)
        return None

    def _table(self) -> Table:
        header: list[list[Inline]] = []
        rows: list[list[list[Inline]]] = []
        aligns: list[str] = []
        current: list[list[Inline]] | None = None
        in_head = False
        while self.i < len(self.t):
            tok = self.t[self.i]
            self.i += 1
            if tok.type == "table_close":
                break
            if tok.type == "thead_open":
                in_head = True
            elif tok.type == "thead_close":
                in_head = False
            elif tok.type == "tr_open":
                current = []
            elif tok.type == "tr_close":
                if in_head:
                    header = current or []
                else:
                    rows.append(current or [])
            elif tok.type in ("th_open", "td_open"):
                style = str(tok.attrs.get("style", ""))
                if in_head:
                    aligns.append(style.replace("text-align:", "").strip())
                inl = self._inline()
                self.i += 1
                assert current is not None
                current.append(_mark_pendientes(_Inlines(inl).parse()))
        return Table(header, rows, aligns)

    def _footnotes(self) -> None:
        while self.i < len(self.t):
            tok = self.t[self.i]
            self.i += 1
            if tok.type == "footnote_block_close":
                return
            if tok.type == "footnote_open":
                label = str(tok.meta.get("label", tok.meta.get("id")))
                body = self.parse("footnote_close")
                self.footnotes[label] = body
            # footnote_anchor tokens viven dentro de los párrafos y se ignoran


def _quote_or_callout(inner: list[Block]) -> Block:
    if inner and isinstance(inner[0], Paragraph) and len(inner[0].children) == 1 and isinstance(inner[0].children[0], Text):
        m = _CALLOUT_MARK.match(inner[0].children[0].text.strip())
        if m and m.group(1).upper() in CALLOUT_KINDS:
            title = m.group(2).strip() or None
            return Callout(CALLOUT_KINDS[m.group(1).upper()], title, list(inner[1:]))
    return Quote(inner)


_CALLOUT_MARK = re.compile(r"^\[!([A-Za-zÁÉÍÓÚáéíóú]+)\]\u241f(.*)$", re.S)
_CALLOUT_LINE = re.compile(r"^([ \t]*>[ \t]*)\[!([A-Za-zÁÉÍÓÚáéíóú]+)\][ \t]*(.*)$", re.MULTILINE)


def _preprocess(src: str) -> str:
    """Aísla la línea ``> [!AVISO] Título`` en su propio párrafo (``[!AVISO]␟Título``)
    para que el título no se mezcle con el cuerpo de la alerta."""

    def repl(m: re.Match) -> str:
        if m.group(2).upper() not in CALLOUT_KINDS:
            return m.group(0)
        return f"{m.group(1)}[!{m.group(2)}]\u241f{m.group(3).strip()}\n{m.group(1).rstrip()}"

    return _CALLOUT_LINE.sub(repl, src)


def read_markdown(src: str, *, chapter_level: int | None = None) -> Document:
    src = src.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    md = _md()
    tokens = md.parse(_preprocess(src))
    meta: dict = {}
    if tokens and tokens[0].type == "front_matter":
        try:
            loaded = yaml.safe_load(tokens[0].content) or {}
            if isinstance(loaded, dict):
                meta = {str(k): v for k, v in loaded.items()}
        except yaml.YAMLError:
            pass
        tokens = tokens[1:]
    footnotes: dict = {}
    blocks = _Blocks(tokens, footnotes).parse()
    doc = split_chapters(blocks, meta, chapter_level=chapter_level or meta.get("chapter_level"))
    doc.footnotes = footnotes
    return doc


def split_chapters(blocks: list[Block], meta: dict, chapter_level: int | None = None) -> Document:
    """Agrupa bloques en capítulos por el nivel de encabezado más alto presente."""
    levels = [b.level for b in blocks if isinstance(b, Heading)]
    if chapter_level is None:
        chapter_level = min(levels) if levels else 1
        # Un único H1 seguido de H2 es el título del libro, no un capítulo.
        if levels.count(chapter_level) == 1 and chapter_level == 1 and 2 in levels and not meta.get("title"):
            idx = next(i for i, b in enumerate(blocks) if isinstance(b, Heading) and b.level == 1)
            if idx == 0 or all(not isinstance(b, Heading) for b in blocks[:idx]):
                meta["title"] = inline_text(blocks[idx].children).strip()
                blocks = blocks[:idx] + blocks[idx + 1:]
                chapter_level = 2
    chapter_level = int(chapter_level)
    doc = Document(meta=meta)
    current: Chapter | None = None
    for b in blocks:
        if isinstance(b, Heading) and b.level == chapter_level:
            current = Chapter(b.children, [], kicker=b.kicker, numbered=b.numbered)
            doc.chapters.append(current)
            continue
        if isinstance(b, Heading) and b.level > chapter_level:
            b = Heading(b.level - chapter_level + 1, b.children, b.kicker, b.numbered)
        if current is None:
            doc.front.append(b)
        else:
            current.blocks.append(b)
    # Primera línea suelta como título (manuscritos sin front matter).
    if not doc.meta.get("title") and doc.front and isinstance(doc.front[0], Paragraph):
        first = inline_text(doc.front[0].children).strip()
        if 0 < len(first) <= 140 and "\n" not in first:
            doc.meta["title"] = first
            doc.front = doc.front[1:]
    doc.number_chapters()
    return doc


def read_inline(src: str) -> list[Inline]:
    """Markdown en línea (sin bloques) → inlines; para campos del front matter."""
    tokens = _md().parseInline(src.strip())
    if not tokens:
        return []
    return _mark_pendientes(_Inlines(tokens[0].children or []).parse())
