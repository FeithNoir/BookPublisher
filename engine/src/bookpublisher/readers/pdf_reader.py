"""PDF → ``Document`` (importación).

Reconstruye la estructura de un PDF compuesto (libro, manual, novela):

* quita cabeceras, pies y folios repetidos,
* une palabras cortadas a final de línea y párrafos partidos entre páginas,
* detecta títulos por tamaño y peso, y su «antetítulo» (CAPÍTULO III, ANEXO A…),
* recupera cursivas, negritas, la cruz † y las marcas «Pendiente de consultar»,
* reconoce listas por sangría o viñeta, tablas con filetes, notas al pie,
* extrae imágenes (sin fondos ni adornos repetidos),
* lee la portada como metadatos y descarta el índice (se regenera al exportar).

Usa PyMuPDF por velocidad: cientos de páginas por segundo.
"""

from __future__ import annotations

import re
import statistics
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from ..model import (
    Block, CodeSpan, Document, Emph, FootnoteRef, Heading, Image, Inline, ListBlock, ListItem,
    Paragraph, SmallCaps, Span, Strong, Table, Text, inline_text,
)
from .markdown_reader import split_chapters

BULLETS = "•◦▪▫◆◇■□●○–‣⁃∙·*"
_ROMAN = re.compile(r"^(?=[ivxlcdm]+$)m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)
_PAGE_NUM = re.compile(r"^[\s·\-–—]*(\d{1,4}|[ivxlcdm]{1,7})[\s·\-–—]*$", re.I)
_KICKER = re.compile(
    r"^(cap[ií]tulo|chapter|parte|libro|pre[aá]mbulo|pr[oó]logo|ep[ií]logo|anexo|ap[eé]ndice|"
    r"interludio|introducci[oó]n|colof[oó]n|[ií]ndice)\b", re.I)
_NUMBERED_KICKER = re.compile(r"^(cap[ií]tulo|chapter)\s+([ivxlcdm]+|\d+)$", re.I)
_TERMINAL = tuple(".!?:;…»”\")]—")
_LIGATURES = str.maketrans({"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"})
_HYPHENS = ("-", "\u2010", "\u2011", "\u00ad")


@dataclass
class Style:
    bold: bool = False
    italic: bool = False
    red: bool = False
    sup: bool = False


@dataclass
class Run:
    text: str
    style: Style
    size: float
    sc: bool = False  # versalitas sintéticas (mayúscula a cuerpo + resto en mayúsculas pequeñas)


@dataclass
class Line:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    runs: list[Run]
    size: float  # tamaño dominante
    page_w: float
    page_h: float

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


class ImportCancelled(Exception):
    """El usuario canceló la importación."""


class PdfImportError(ValueError):
    """El archivo no se puede importar (no es un PDF, está protegido o no tiene texto)."""


@dataclass
class ImportReport:
    pages: int = 0
    removed_headers: list[str] = field(default_factory=list)
    removed_lines: int = 0
    joined_hyphens: int = 0
    joined_across_pages: int = 0
    tables: int = 0
    images: int = 0
    footnotes: int = 0
    skipped_toc_pages: list[int] = field(default_factory=list)
    cover_page: bool = False
    warnings: list[str] = field(default_factory=list)


Progress = Callable[[dict], None]


class _Fonts:
    """Resuelve negrita/cursiva también en fuentes Type3 (leyendo su FontDescriptor)."""

    def __init__(self, doc):
        self.doc = doc
        self.cache: dict[str, tuple[bool, bool]] = {}

    def style(self, name: str, flags: int) -> tuple[bool, bool]:
        key = f"{name}|{flags}"
        if key in self.cache:
            return self.cache[key]
        low = name.lower()
        bold = bool(flags & 16) or any(w in low for w in ("bold", "black", "heavy", "semibold", "demi"))
        italic = bool(flags & 2) or any(w in low for w in ("italic", "oblique", "-it", "kursiv"))
        m = re.match(r"Type3 \((\d+) 0 R\)", name)
        if m:
            try:
                obj = self.doc.xref_object(int(m.group(1)))
                fd = re.search(r"/FontDescriptor (\d+) 0 R", obj)
                if fd:
                    d = self.doc.xref_object(int(fd.group(1)))
                    w = re.search(r"/FontWeight (\d+)", d)
                    a = re.search(r"/ItalicAngle (-?[\d.]+)", d)
                    fn = re.search(r"/FontName /(\S+)", d)
                    if w:
                        bold = int(w.group(1)) >= 600
                    if a and float(a.group(1)) != 0:
                        italic = True
                    if fn and "italic" in fn.group(1).lower():
                        italic = True
                    if fn and "bold" in fn.group(1).lower():
                        bold = True
            except Exception:  # pragma: no cover - PDF raros
                pass
        self.cache[key] = (bold, italic)
        return bold, italic


def _is_red(color: int) -> bool:
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return r > 110 and r > g + 45 and r > b + 45


# ------------------------------------------------------------- extraction
def _extract_lines(doc, report: ImportReport, progress: Progress, cancel: threading.Event,
                   with_images: bool, with_tables: bool):
    import pymupdf as fitz

    fonts = _Fonts(doc)
    flags = (fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_INHIBIT_SPACES
             | fitz.TEXT_MEDIABOX_CLIP)
    pages: list[list[Line]] = []
    images: list[tuple[int, float, str, bytes]] = []  # página, y, nombre, bytes
    tables: dict[int, list] = {}
    image_seen: Counter = Counter()
    n = doc.page_count
    for pno in range(n):
        if cancel.is_set():
            raise ImportCancelled()
        page = doc[pno]
        pw, ph = page.rect.width, page.rect.height
        data = page.get_text("dict", flags=flags)
        lines: list[Line] = []
        for b in data["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                if ln.get("dir", (1, 0))[1] != 0:  # texto vertical: fuera
                    continue
                runs: list[Run] = []
                sizes: Counter = Counter()
                for s in ln["spans"]:
                    t = s["text"].translate(_LIGATURES)
                    if not t:
                        continue
                    bold, italic = fonts.style(s["font"], s["flags"])
                    st = Style(bold, italic, _is_red(s["color"]), bool(s["flags"] & 1))
                    if runs and runs[-1].style == st and abs(runs[-1].size - s["size"]) < 0.6:
                        runs[-1].text += t
                    else:
                        runs.append(Run(t, st, s["size"]))
                    sizes[round(s["size"], 1)] += len(t.strip())
                if not runs or not "".join(r.text for r in runs).strip():
                    continue
                x0, y0, x1, y1 = ln["bbox"]
                size = sizes.most_common(1)[0][0] if sizes else runs[0].size
                runs = _small_caps(runs, size)
                lines.append(Line(pno, x0, y0, x1, y1, runs, size, pw, ph))
        lines.sort(key=lambda l: (round(l.y0 / 3), l.x0))
        pages.append(lines)

        if with_tables:
            try:
                drawings = page.get_drawings()
                if len(drawings) >= 12:
                    found = page.find_tables()
                    if found.tables:
                        tables[pno] = found.tables
            except Exception:  # pragma: no cover
                report.warnings.append(f"No se pudieron leer tablas en la página {pno + 1}.")
        if with_images:
            for info in page.get_images(full=True):
                xref = info[0]
                image_seen[xref] += 1
                try:
                    rects = page.get_image_rects(xref)
                except Exception:
                    rects = []
                for r in rects:
                    area = r.width * r.height
                    if area > 0.8 * pw * ph or r.width < 40 or r.height < 40:
                        continue  # fondos y adornos
                    images.append((pno, r.y0, xref, r))
        if progress and (pno % 5 == 0 or pno == n - 1):
            progress({"type": "page", "done": pno + 1, "total": n})
    # Imágenes que se repiten en muchas páginas son adornos.
    out_images = []
    for pno, y, xref, rect in images:
        if image_seen[xref] > max(3, n * 0.3):
            continue
        if pno == 0:
            # En portadas la imagen suele ir recortada por un trazado (escudos, sellos):
            # se toma tal como se ve en la página.
            data, ext = doc[0].get_pixmap(clip=rect, dpi=200).tobytes("png"), "png"
        else:
            data, ext = _image_bytes(doc, xref)
        if data is None:
            continue
        name = f"imagen-{pno + 1:03d}-{xref}.{ext}"
        out_images.append((pno, y, name, data, rect))
    return pages, out_images, tables


def _image_bytes(doc, xref: int) -> tuple[bytes | None, str]:
    """Bytes de la imagen; si tiene máscara de transparencia (SMask) se combina en un PNG con alfa."""
    import pymupdf

    try:
        img = doc.extract_image(xref)
    except Exception:  # noqa: BLE001
        return None, ""
    smask = img.get("smask") or 0
    if not smask:
        return img["image"], img.get("ext", "png")
    try:
        base = pymupdf.Pixmap(doc, xref)
        if base.alpha:
            base = pymupdf.Pixmap(base, 0)
        if base.colorspace and base.colorspace.n > 3:
            base = pymupdf.Pixmap(pymupdf.csRGB, base)
        mask = pymupdf.Pixmap(doc, smask)
        return pymupdf.Pixmap(base, mask).tobytes("png"), "png"
    except Exception:  # noqa: BLE001
        return img["image"], img.get("ext", "png")


def _norm_header(s: str) -> str:
    s = re.sub(r"\d+", "#", s.lower())
    s = re.sub(r"\b[ivxlcdm]{1,7}\b", "#", s)
    return re.sub(r"[\s·\-–—|]+", " ", s).strip()


def _strip_furniture(pages: list[list[Line]], report: ImportReport) -> None:
    n = len(pages)
    counts: Counter = Counter()
    for lines in pages:
        seen = set()
        for l in lines:
            if l.y1 < l.page_h * 0.1 or l.y0 > l.page_h * 0.9:
                k = _norm_header(l.text)
                if k and k not in seen:
                    seen.add(k)
                    counts[k] += 1
    threshold = max(2, int(n * 0.3))
    repeated = {k for k, c in counts.items() if c >= threshold and n >= 3}
    report.removed_headers = sorted(repeated)[:10]
    for i, lines in enumerate(pages):
        keep = []
        for l in lines:
            edge = l.y1 < l.page_h * 0.1 or l.y0 > l.page_h * 0.9
            if edge and (_norm_header(l.text) in repeated or _PAGE_NUM.match(l.text.strip())
                         or not any(ch.isalnum() for ch in l.text)):  # restos de adornos («· ·»)
                report.removed_lines += 1
                continue
            keep.append(l)
        pages[i] = keep


def _body_metrics(pages: list[list[Line]]) -> tuple[float, float, float, float]:
    sizes: Counter = Counter()
    lefts: Counter = Counter()
    rights: Counter = Counter()
    pitches: list[float] = []
    for lines in pages:
        prev = None
        for l in lines:
            sizes[round(l.size, 1)] += len(l.text)
        for l in lines:
            if prev is not None and abs(l.size - prev.size) < 0.3 and 0 < l.y0 - prev.y0 < prev.size * 3:
                pitches.append(l.y0 - prev.y0)
            prev = l
    body = sizes.most_common(1)[0][0] if sizes else 11.0
    for lines in pages:
        for l in lines:
            if abs(l.size - body) < 0.3:
                lefts[round(l.x0)] += 1
                rights[round(l.x1)] += 1
    left = lefts.most_common(1)[0][0] if lefts else 72
    right = max((x for x, c in rights.items() if c >= max(3, rights.most_common(1)[0][1] * 0.2)), default=left + 400) if rights else left + 400
    pitch = statistics.median(pitches) if pitches else body * 1.4
    return body, left, right, pitch


def _is_toc_page(lines: list[Line]) -> bool:
    if len(lines) < 4:
        return False
    numeric = sum(1 for l in lines if re.search(r"(\s|\.{2,}|…)(\d{1,4}|[ivxlc]{1,6})$", l.text.strip())
                  or re.fullmatch(r"\d{1,4}", l.text.strip()))
    has_title = any(re.search(r"\b([ií]ndice|contenido|sumario|registro de)", l.text, re.I) for l in lines[:6])
    return (numeric >= len(lines) * 0.3 and has_title) or numeric >= max(6, len(lines) * 0.45)


# --------------------------------------------------------------- inlines
def _small_caps(runs: list[Run], size: float) -> list[Run]:
    """Los navegadores imprimen las versalitas como «B» a cuerpo + «ucara» más pequeño.
    Se reconstruye la palabra («Bucara») y se marca como versalita."""
    out: list[Run] = []
    for r in runs:
        small = 0.6 < r.size / max(size, 1) < 0.86 and r.text[:1].isalpha() and not r.style.sup
        prev = out[-1] if out else None
        if small and prev is not None and prev.text and prev.text[-1].isupper() and not prev.sc:
            cap = prev.text[-1]
            prev.text = prev.text[:-1]
            if not prev.text:
                out.pop()
            out.append(Run(cap + r.text, r.style, size, sc=True))
            continue
        # Palabra entera en minúscula dentro de una versalita («Posta di Donna»).
        if small and r.text.strip().isalpha() and r.text.strip().islower() and prev is not None and (
                prev.sc or (not prev.text.strip() and len(out) > 1 and out[-2].sc)):
            out.append(Run(r.text, r.style, size, sc=True))
            continue
        out.append(r)
    return out


def _runs_to_inlines(runs: list[Run]) -> list[Inline]:
    out: list[Inline] = []
    for r in runs:
        if not r.text:
            continue
        if r.sc:
            word = r.text.rstrip()
            if (len(out) >= 2 and isinstance(out[-2], SmallCaps) and isinstance(out[-1], Text)
                    and out[-1].text in (" ", "\u00a0")):  # «Bucara» + « » + «Geek» → una sola versalita
                sep = out.pop().text
                out[-1].children.append(Text(sep + word))
            else:
                node: Inline = SmallCaps([Text(word)])
                if r.style.italic:
                    node = Emph([node])
                if r.style.bold:
                    node = Strong([node])
                out.append(node)
            if r.text != word:
                out.append(Text(r.text[len(word):]))
            continue
        if r.style.sup and r.text.strip().isdigit():
            out.append(FootnoteRef(r.text.strip()))
            continue
        node: Inline = Text(r.text)
        if not any(ch.isalnum() for ch in r.text):
            out.append(node)  # «†», comas o rayas sueltas: sin énfasis
            continue
        if r.style.italic:
            node = Emph([node])
        if r.style.bold:
            node = Strong([node])
        out.append(node)
    return _merge_inlines(out)


def _merge_inlines(nodes: list[Inline]) -> list[Inline]:
    # «**A** **B**» → «**A B**» (y lo mismo con versalitas): un solo espacio no corta el estilo.
    joined: list[Inline] = []
    for n in nodes:
        if (len(joined) >= 2 and isinstance(n, (Strong, Emph, SmallCaps)) and type(joined[-2]) is type(n)
                and isinstance(joined[-1], Text) and joined[-1].text == " "):
            joined.pop()
            joined[-1].children = joined[-1].children + [Text(" ")] + n.children
        else:
            joined.append(n)
    nodes = joined
    out: list[Inline] = []
    for n in nodes:
        if out and type(out[-1]) is type(n) and isinstance(n, (Emph, Strong, SmallCaps)):
            out[-1].children = _merge_inlines(out[-1].children + n.children)
        elif out and isinstance(out[-1], Text) and isinstance(n, Text):
            out[-1] = Text(out[-1].text + n.text)
        else:
            out.append(n)
    # Los espacios en los bordes de cursivas/negritas se sacan fuera (Markdown los exige así).
    fixed: list[Inline] = []
    for n in out:
        if isinstance(n, (Emph, Strong)):
            t = inline_text(n.children)
            lead = t[: len(t) - len(t.lstrip())]
            trail = t[len(t.rstrip()):]
            if not t.strip():
                fixed.append(Text(t))
                continue
            _trim(n, lead, trail)
            if lead:
                fixed.append(Text(lead))
            fixed.append(n)
            if trail:
                fixed.append(Text(trail))
        else:
            fixed.append(n)
    res: list[Inline] = []
    for n in fixed:
        if res and isinstance(res[-1], Text) and isinstance(n, Text):
            res[-1] = Text(res[-1].text + n.text)
        else:
            res.append(n)
    return res


def _trim(node, lead: str, trail: str) -> None:
    kids = node.children
    if lead and kids:
        first = kids[0]
        if isinstance(first, Text):
            kids[0] = Text(first.text[len(lead):] if first.text.startswith(lead) else first.text.lstrip())
        elif hasattr(first, "children"):
            _trim(first, lead, "")
    if trail and kids:
        last = kids[-1]
        if isinstance(last, Text):
            kids[-1] = Text(last.text[: len(last.text) - len(trail)] if last.text.endswith(trail) else last.text.rstrip())
        elif hasattr(last, "children"):
            _trim(last, "", trail)


def _mark_pendiente(nodes: list[Inline], runs: list[Run]) -> list[Inline]:
    """Cursiva roja que empieza por «Pendiente de consultar» → span .pendiente."""
    out = []
    for n in nodes:
        if isinstance(n, Emph) and re.match(r"\s*pendiente de consultar", inline_text(n.children), re.I):
            out.append(Span("pendiente", n.children))
        else:
            out.append(n)
    return out


# ---------------------------------------------------------- paragraphs
@dataclass
class Para:
    lines: list[Line]
    kind: str = "p"  # p | h | li | caption
    level: int = 0
    dropcap: str = ""


def _join_runs(paras_lines: list[Line], report: ImportReport) -> list[Run]:
    runs: list[Run] = []
    for i, l in enumerate(paras_lines):
        lr = [Run(r.text, r.style, r.size, r.sc) for r in l.runs]
        if i > 0 and runs:
            prev = runs[-1]
            pt = prev.text.rstrip()
            nxt = l.text.lstrip()
            if pt.endswith(_HYPHENS) and not pt.endswith("--") and nxt[:1].islower() and len(pt) > 1 and pt[-2].isalpha():
                prev.text = pt[:-1]
                report.joined_hyphens += 1
                lr[0].text = lr[0].text.lstrip()
            elif not prev.text.endswith((" ", "\u00a0")) and not pt.endswith("/") and not (
                    pt.endswith("—") and (len(pt) == 1 or pt[-2] in " («“")):
                prev.text = pt + " "
                lr[0].text = lr[0].text.lstrip()
        for r in lr:
            if runs and runs[-1].style == r.style and runs[-1].sc == r.sc and not r.sc:
                runs[-1].text += r.text
            else:
                runs.append(r)
    if runs:
        runs[-1].text = runs[-1].text.rstrip()
        runs[0].text = runs[0].text.lstrip()
    return runs


def _group(pages: list[list[Line]], body: float, left: float, right: float, pitch: float,
           report: ImportReport) -> list[tuple[int, float, Para]]:
    """Agrupa líneas en párrafos. Devuelve (página, y, párrafo)."""
    out: list[tuple[int, float, Para]] = []
    width = right - left
    for pno, lines in enumerate(pages):
        # Capitulares: una letra enorme se pega a la línea que tiene a su derecha.
        caps = [l for l in lines if len(l.text.strip()) == 1 and l.text.strip().isalpha() and l.size > body * 2.2]
        rest = [l for l in lines if l not in caps]
        pending_caps = {}
        for c in caps:
            target = min((l for l in rest if l.x0 > c.x1 - 2 and c.y0 - body < l.y0 < c.y1),
                         key=lambda l: l.y0, default=None)
            if target is not None:
                pending_caps[id(target)] = c.text.strip()
        cur: Para | None = None
        prev: Line | None = None
        for l in rest:
            txt = l.text.strip()
            is_big = l.size > body * 1.18
            is_head_bold = (all(r.style.bold for r in l.runs if r.text.strip()) and l.size >= body * 0.98
                            and len(txt) < 90 and not txt.endswith((".", ",", ";")))
            centered = abs((l.x0 + l.x1) / 2 - (left + right) / 2) < 12 and (l.x1 - l.x0) < width * 0.8
            first_char = txt[:1]
            bullet = first_char in BULLETS and len(txt) > 2 and txt[1:2] in (" ", "\u00a0")
            numbered = re.match(r"^\d{1,2}[.)]\s", txt) is not None
            indent = l.x0 - left
            new = False
            kind = "p"
            if is_big or (is_head_bold and (prev is None or l.y0 - prev.y1 > pitch * 0.6)):
                kind = "h"
            elif bullet or numbered:
                kind = "li"
            elif l.size < body * 0.93 and l.size > body * 0.6 and not centered:
                kind = "small"
            if id(l) in pending_caps:
                new = True
            elif cur is None or prev is None:
                new = True
            elif kind != cur.kind and not (cur.kind == "li" and kind == "p" and indent > 6):
                new = True
            elif kind == "li":
                new = True
            elif kind == "h":
                new = abs(l.size - prev.size) > 0.5 or l.y0 - prev.y1 > l.size * 0.9
            else:
                gap = l.y0 - prev.y0
                if gap > pitch * 1.15 or gap < 0:
                    new = True
                elif abs(l.size - prev.size) > 0.6:
                    new = True
                elif indent > body * 0.8 and indent < width * 0.25 and cur.kind == "p" and abs(prev.x0 - left) < 3 \
                        and cur.lines[0].x0 - left < 3 and not centered:
                    new = True  # sangría de primera línea (novelas)
                elif prev.x1 < left + width * 0.82 and prev.text.rstrip().endswith(_TERMINAL) and not centered:
                    new = True  # la línea anterior era la última del párrafo
            if new:
                cur = Para([l], kind)
                if id(l) in pending_caps:
                    cur.dropcap = pending_caps[id(l)]
                out.append((pno, l.y0, cur))
            else:
                cur.lines.append(l)
            prev = l
    return out


def _cover_meta(lines: list[Line], body: float) -> dict:
    meta: dict = {}
    if not lines:
        return meta
    biggest = max(l.size for l in lines)
    title_lines = [l for l in lines if l.size >= biggest * 0.8]
    meta["title"] = " ".join(l.text.strip() for l in title_lines)
    if meta["title"].isupper():
        meta["title"] = _smart_title(meta["title"])
    t_top = min(l.y0 for l in title_lines)
    t_bot = max(l.y1 for l in title_lines)
    above = [l for l in lines if l.y1 <= t_top and l not in title_lines]
    below = [l for l in lines if l.y0 >= t_bot and l not in title_lines]
    if above:
        meta["kicker"] = " ".join(l.text.strip() for l in above)
    # Bloques debajo del título agrupados por cercanía vertical.
    groups: list[list[Line]] = []
    for l in below:
        if groups and l.y0 - groups[-1][-1].y1 < l.size * 1.2 and abs(l.size - groups[-1][-1].size) < 0.8:
            groups[-1].append(l)
        else:
            groups.append([l])
    texts = []
    for g in groups:
        italic = all(r.style.italic for l in g for r in l.runs if r.text.strip())
        t = " ".join(l.text.strip() for l in g)
        texts.append((t, italic, g[0].y0, g[0].page_h))
    italics = [t for t, it, *_ in texts if it]
    plain = [(t, y, h) for t, it, y, h in texts if not it]
    if italics:
        meta["subtitle"] = italics[0]
    if len(italics) > 1:
        meta["description"] = " ".join(italics[1:])
    bottom = [t for t, y, h in plain if y > h * 0.85]
    middle = [t for t, y, h in plain if y <= h * 0.85]
    if middle:
        meta["place"] = middle[0]
    if len(middle) > 1:
        meta["edition"] = " · ".join(middle[1:])
    if bottom:
        meta["colophon_line"] = bottom[-1].strip("· ").strip()
    return meta


_LOWER_WORDS = {"de", "del", "la", "las", "el", "los", "y", "e", "o", "u", "en", "a", "al", "con", "por", "para", "sin", "sobre"}


def _smart_title(s: str) -> str:
    words = s.lower().split()
    return " ".join(w if (i and w in _LOWER_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(words))


def _smart_case(s: str) -> str:
    if not s.isupper():
        return s
    out = s.lower()
    out = re.sub(r"(^|[·—.]\s*)(\w)", lambda m: m.group(1) + m.group(2).upper(), out)
    # Romanos y siglas cortas de vuelta a mayúsculas.
    out = re.sub(r"\b([ivxlcdm]{2,})\b", lambda m: m.group(1).upper() if _ROMAN.match(m.group(1)) else m.group(1), out)
    return out


def _kicker_text(s: str) -> str:
    s = s.strip()
    if not s.isupper():
        return s
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        if len(w) == 1 and i == len(words) - 1 or _ROMAN.match(w) and i > 0:
            out.append(w.upper())
        elif i == 0:
            out.append(w[:1].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


def _toc_meta(lines: list[Line], body: float) -> dict:
    meta: dict = {}
    entries = [l for l in lines if re.search(r"(?:^|\s)(\d{1,4}|[ivxlc]{1,6})$", l.text.strip())]
    if not entries:
        return meta
    first_entry = min(l.y0 for l in entries)
    last_entry = max(l.y1 for l in entries)
    head = [l for l in lines if l.y1 <= first_entry]
    if head:
        big = max(head, key=lambda l: l.size)
        small = [l for l in head if l is not big and l.y0 < big.y0]
        meta["toc_title"] = big.text.strip()
        if small:
            meta["toc_kicker"] = _kicker_text(" ".join(l.text.strip() for l in small))
    toc: list[tuple[str, str]] = []
    for l in lines:
        runs = [r for r in l.runs if r.text.strip()]
        if len(runs) < 2:
            continue
        lab = runs[0].text.strip()
        if runs[0].style.red and re.fullmatch(r"[—–-]|[IVXLCDM]{1,6}|[A-Z]|\d{1,3}", lab):
            title = re.sub(r"[\s.·…]*(\d{1,4}|[ivxlc]{1,6})$", "", "".join(r.text for r in runs[1:]).strip())
            toc.append((lab, title.strip()))
    meta["_toc_entries"] = toc
    tail = [l for l in lines if l.y0 >= last_entry + 2]
    if tail:
        text = " ".join(l.text.strip() for l in tail)
        m = re.match(r"^(aviso al lector\.?|nota\.?|advertencia\.?)\s*(.*)$", text, re.I)
        if m:
            meta["toc_note_title"] = m.group(1).strip().capitalize()
            text = m.group(2)
        meta["toc_note"] = re.sub(r"(\w)- (\w)", r"\1\2", text)
    return meta


# ------------------------------------------------------------------ main
def read_pdf(path: str, *, progress: Progress | None = None, cancel: threading.Event | None = None,
             with_images: bool = True, with_tables: bool = True, detect_cover: bool = True,
             skip_toc: bool = True) -> tuple[Document, ImportReport]:
    import pymupdf as fitz

    progress = progress or (lambda e: None)
    cancel = cancel or threading.Event()
    report = ImportReport()
    try:
        doc = fitz.open(path, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise PdfImportError("El archivo no parece un PDF válido.") from e
    if doc.needs_pass:
        doc.close()
        raise PdfImportError("El PDF está protegido con contraseña; ábrelo y guárdalo sin protección antes de importarlo.")
    report.pages = doc.page_count
    try:
        pages, images, tables = _extract_lines(doc, report, progress, cancel, with_images, with_tables)
        meta_pdf = doc.metadata or {}
    finally:
        doc.close()
    _strip_furniture(pages, report)
    body, left, right, pitch = _body_metrics(pages)
    meta: dict = {}

    # Portada: primera página con pocas palabras y un tamaño muy grande.
    if detect_cover and pages and pages[0]:
        words = sum(len(l.text.split()) for l in pages[0])
        if words < 160 and max(l.size for l in pages[0]) > body * 2:
            meta.update(_cover_meta(pages[0], body))
            report.cover_page = True
            pages[0] = []
    # Índices: se descartan (BookPublisher los regenera), pero su título se conserva.
    if skip_toc:
        for i, lines in enumerate(pages[:8]):
            if _is_toc_page(lines):
                meta.update(_toc_meta(lines, body))
                report.skipped_toc_pages.append(i + 1)
                pages[i] = []
    if not meta.get("title") and meta_pdf.get("title"):
        meta["title"] = meta_pdf["title"]
    if meta_pdf.get("author"):
        meta.setdefault("author", meta_pdf["author"])

    # Quitar de las páginas las líneas que caen dentro de tablas.
    table_blocks: list[tuple[int, float, Block]] = []
    for pno, tbs in tables.items():
        for tb in tbs:
            x0, y0, x1, y1 = tb.bbox
            inside = [l for l in pages[pno] if l.y0 >= y0 - 2 and l.y1 <= y1 + 2 and l.x0 >= x0 - 2 and l.x1 <= x1 + 2]
            if not inside:
                continue
            tbl = _table_from(tb, inside)
            if tbl is None:
                continue
            pages[pno] = [l for l in pages[pno] if l not in inside]
            table_blocks.append((pno, y0, tbl))
            report.tables += 1

    paras = _group(pages, body, left, right, pitch, report)
    items: list[tuple[int, float, int, object]] = []
    for pno, y, p in paras:
        items.append((pno, y, 0, p))
    for pno, y, t in table_blocks:
        items.append((pno, y, 1, t))
    assets: dict[str, bytes] = {}
    for pno, y, name, data, rect in images:
        if report.cover_page and pno == 0:
            assets[name] = data
            meta["cover_image"] = name
            continue
        assets[name] = data
        items.append((pno, y, 2, Image(name, "")))
        report.images += 1
    items.sort(key=lambda it: (it[0], it[1], it[2]))

    blocks: list[Block] = []
    sizes = sorted({round(p.lines[0].size) for _, _, k, p in items if k == 0 and p.kind == "h"}, reverse=True)
    footnotes: dict[str, list[Block]] = {}
    pending_kicker: str | None = None
    last_para: Paragraph | None = None
    last_page = -1
    last_open = False  # el último párrafo quedó sin cerrar (sigue en otra página)
    caption_open: Image | None = None
    for pno, y, k, obj in items:
        if k == 1 and blocks and isinstance(blocks[-1], Table) and len(blocks[-1].header) == len(obj.header):
            # Tabla que sigue en la página siguiente: misma tabla, su «encabezado» es una fila.
            blocks[-1].rows.append(obj.header)
            blocks[-1].rows.extend(obj.rows)
            continue
        if k != 0:
            blocks.append(obj)  # type: ignore[arg-type]
            last_para = None
            continue
        p: Para = obj  # type: ignore[assignment]
        runs = _join_runs(p.lines, report)
        if p.dropcap and runs:
            runs[0].text = p.dropcap + runs[0].text
        text = "".join(r.text for r in runs).strip()
        if not text:
            continue
        first = p.lines[0]
        # Antetítulos («CAPÍTULO III», «PREÁMBULO»…) pequeños, en versal y aislados.
        if len(text) < 40 and _KICKER.match(text) and (text.isupper() or all(r.style.red for r in runs if r.text.strip())):
            pending_kicker = text
            continue
        if p.kind == "h":
            level = (sizes.index(round(first.size)) + 1) if round(first.size) in sizes else 2
            if first.size <= body * 1.18:
                level = max(level, len(sizes) + 1)
            h = Heading(min(level, 4), _merge_inlines([Text(text)]))
            if pending_kicker:
                h._had_kicker = True  # type: ignore[attr-defined]
                m = _NUMBERED_KICKER.match(pending_kicker)
                if not m:
                    h.kicker = _kicker_text(pending_kicker)
                    h.numbered = False
                pending_kicker = None
            blocks.append(h)
            last_para = None
            continue
        if pending_kicker:
            blocks.append(Paragraph([Text(pending_kicker)]))
            pending_kicker = None
        # Nota al pie: línea pequeña al final de página que empieza por número.
        m = re.match(r"^(\d{1,3})[.)]?\s+(.+)$", text, re.S)
        if p.kind == "small" and m and first.y0 > first.page_h * 0.6:
            footnotes[m.group(1)] = [Paragraph([Text(m.group(2))])]
            report.footnotes += 1
            continue
        inl = _mark_pendiente(_runs_to_inlines(runs), runs)
        if p.kind == "small" and blocks and isinstance(blocks[-1], Image) and not blocks[-1].caption:
            blocks[-1].caption = [Text(inline_text(inl).strip())]
            blocks[-1].alt = inline_text(inl).strip()[:120]
            caption_open = blocks[-1]
            continue
        if p.kind == "small" and caption_open is not None and blocks and blocks[-1] is caption_open:
            caption_open.caption = [Text(inline_text(caption_open.caption) + " " + inline_text(inl).strip())]
            continue
        caption_open = None
        if p.kind == "li" or (first.x0 - left > 8 and first.x0 - left < 60 and len(p.lines) > 0
                              and (runs[0].style.bold) and p.kind == "p"):
            if inl and isinstance(inl[0], Text):
                t0 = inl[0].text.lstrip()
                if t0[:1] in BULLETS:
                    t0 = t0[1:].lstrip()
                t0 = re.sub(r"^\d{1,2}[.)]\s+", "", t0) if re.match(r"^\d{1,2}[.)]\s", t0) else t0
                inl[0] = Text(t0)
            ordered = re.match(r"^\d{1,2}[.)]\s", text) is not None
            if blocks and isinstance(blocks[-1], ListBlock) and blocks[-1].ordered == ordered:
                blocks[-1].items.append(ListItem([Paragraph(inl)]))
            else:
                blocks.append(ListBlock(ordered, [ListItem([Paragraph(inl)])]))
            last_para = None
            continue
        # Párrafo partido entre páginas: si el anterior no cerró, se une.
        if last_para is not None and pno == last_page + 1 and last_open and text[:1].islower():
            prev_text = inline_text(last_para.children).rstrip()
            if prev_text.endswith(_HYPHENS) and prev_text[-2:-1].isalpha():
                _strip_trailing_hyphen(last_para)
                report.joined_hyphens += 1
            else:
                last_para.children.append(Text(" "))
            last_para.children.extend(inl)
            last_para.children = _merge_inlines(last_para.children)
            report.joined_across_pages += 1
        else:
            last_para = Paragraph(inl)
            blocks.append(last_para)
        last_page = pno
        last_open = not text.endswith(_TERMINAL)

    # Nivel de capítulo: el de los títulos con antetítulo (CAPÍTULO I…), o el más alto.
    heads = [b for b in blocks if isinstance(b, Heading)]
    chapter_level = None
    if heads:
        with_kicker = Counter(b.level for b in heads if b.kicker or getattr(b, "_had_kicker", False))
        chapter_level = with_kicker.most_common(1)[0][0] if with_kicker else min(b.level for b in heads)
        for b in heads:
            if b.level < chapter_level:
                b.level = chapter_level
        # Subniveles consecutivos: 1, 2, 3… sin huecos.
        subs = sorted({b.level for b in heads if b.level > chapter_level})
        remap = {lv: chapter_level + i + 1 for i, lv in enumerate(subs)}
        for b in heads:
            if b.level in remap:
                b.level = remap[b.level]
    toc_entries = meta.pop("_toc_entries", [])
    document = split_chapters(blocks, meta, chapter_level=chapter_level)
    # El índice original dice qué capítulos no llevan número («— Colofón…»).
    for ch in document.chapters:
        t = _norm_header(inline_text(ch.title))
        for lab, title in toc_entries:
            nt = _norm_header(title)
            if nt and (nt == t or nt.endswith(t) or t and t in nt) and lab in "—–-" and ch.numbered:
                ch.numbered = False
    document.number_chapters()
    document.footnotes = footnotes
    document.assets = assets
    if not document.meta.get("title"):
        document.meta["title"] = "Documento importado"
    return document, report


def _strip_trailing_hyphen(p: Paragraph) -> None:
    node = p.children[-1]
    while hasattr(node, "children") and node.children:
        parent, node = node, node.children[-1]
    if isinstance(node, Text):
        new = Text(node.text.rstrip()[:-1])
        if node is p.children[-1]:
            p.children[-1] = new
        else:
            parent.children[-1] = new  # type: ignore[name-defined]


def _table_from(tb, lines: list[Line]) -> Table | None:
    try:
        rows = tb.rows
    except Exception:
        return None
    grid: list[list[list[Inline]]] = []
    for row in rows:
        cells_out: list[list[Inline]] = []
        for cell in row.cells:
            if cell is None:
                cells_out.append([])
                continue
            cx0, cy0, cx1, cy1 = cell
            inside = [l for l in lines if (l.x0 + l.x1) / 2 >= cx0 and (l.x0 + l.x1) / 2 <= cx1
                      and (l.y0 + l.y1) / 2 >= cy0 and (l.y0 + l.y1) / 2 <= cy1]
            inside.sort(key=lambda l: (l.y0, l.x0))
            dummy = ImportReport()
            runs = _join_runs(inside, dummy) if inside else []
            cells_out.append(_mark_pendiente(_runs_to_inlines(runs), runs))
        grid.append(cells_out)
    if len(grid) < 2:
        return None
    header = grid[0]
    # Encabezados en versalitas: «Conducta» etc. quedan como texto plano.
    header = [[Text(inline_text(c))] if c else [] for c in header]
    return Table(header, grid[1:], [""] * len(header))
