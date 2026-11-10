"""Exportación de un ``Document`` a PDF, por fragmentos y en paralelo.

Cada capítulo (o el cuerpo entero, en temas de flujo continuo) es un
fragmento Typst independiente. Los fragmentos se componen en un grupo de
procesos, se guardan en caché por contenido y se unen con PyMuPDF. Así:

* el progreso es real (capítulos y páginas terminadas),
* cancelar no deja procesos colgados,
* volver a exportar tras corregir un capítulo solo recompone lo que cambió,
* la memoria queda acotada a un capítulo por proceso.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import multiprocessing as mp
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from ..model import Chapter, Document, chapter_words, inline_text
from ..themes import THEMES_DIR, get_theme, themes_version
from ..writers.typst_writer import TypstWriter, chapter_label, toc_label, tstr, typst_value
from .normalize import fix_dialogue_dashes, normalize_titles

# Typst memoriza resultados entre compilaciones y cada proceso puede quedarse con
# 150-250 MB tras un libro largo. Si el grupo queda ocioso este tiempo, se cierra
# y la memoria vuelve al sistema (reabrirlo cuesta ~0,3 s).
IDLE_RELEASE_SECONDS = float(os.environ.get("BOOKPUBLISHER_IDLE_RELEASE", "90"))
FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


class ExportCancelled(Exception):
    pass


class RenderError(Exception):
    """Error de composición con contexto legible (capítulo y mensaje de Typst)."""

    def __init__(self, message: str, chapter: str | None = None, detail: str = ""):
        super().__init__(message)
        self.chapter = chapter
        self.detail = detail


@dataclass
class RenderOptions:
    theme: str = "novela"
    page_size: str | None = None
    font_size: float | None = None
    chapter_break: str | None = None  # flow | page | recto
    dropcaps: bool | None = None
    hyphenate: bool = True
    toc: bool = True
    cover: bool = True
    normalize_titles: bool = True

    def resolved(self) -> dict:
        theme = get_theme(self.theme)
        o = dict(theme.defaults)
        for k in ("page_size", "font_size", "chapter_break", "dropcaps"):
            v = getattr(self, k)
            if v is not None:
                o[k] = v
        o["hyphenate"] = self.hyphenate
        return o


@dataclass
class Chunk:
    index: int
    chapters: list[int]
    source: str  # contiene «@@START@@» donde va la página inicial
    words: int
    key: str = ""
    pages: int = 0
    pad: bool = False  # añade una página en blanco para que el siguiente abra en impar
    start: int = 1
    cached: bool = False
    chapter_pages: dict = field(default_factory=dict)  # índice de capítulo → página física
    sections: list = field(default_factory=list)


@dataclass
class ExportResult:
    path: str
    pages: int
    seconds: float
    size_bytes: int
    chapters: int
    words: int
    chunks: int
    cached_chunks: int
    phases: dict
    warnings: list[str]

    def to_json(self) -> dict:
        return asdict(self)


Progress = Callable[[dict], None]


# --------------------------------------------------------------- runtime
class Runtime:
    """Carpeta raíz de Typst con temas, recursos y caché de fragmentos."""

    def __init__(self, base: Path | None = None, workers: int | None = None):
        base = base or Path(os.environ.get("BOOKPUBLISHER_CACHE", Path.home() / ".cache" / "bookpublisher"))
        self.base = Path(base)
        self.root = self.base / "root"
        self.cache = self.base / "chunks"
        self.work = self.root / "work"
        self.assets = self.root / "assets"
        for p in (self.root, self.cache, self.work, self.assets):
            p.mkdir(parents=True, exist_ok=True)
        self._sync_themes()
        self.workers = workers or default_workers()
        self._pool: cf.ProcessPoolExecutor | None = None
        self._lock = threading.Lock()
        self._last_use = time.monotonic()
        self._busy = 0
        self._reaper: threading.Thread | None = None

    def _sync_themes(self) -> None:
        dest = self.root / "themes"
        stamp = dest / ".version"
        if stamp.exists() and stamp.read_text() == themes_version():
            return
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(THEMES_DIR, dest, ignore=shutil.ignore_patterns("__pycache__", "*.py", "*.json"))
        stamp.write_text(themes_version())

    @property
    def pool(self) -> cf.ProcessPoolExecutor:
        self._last_use = time.monotonic()
        with self._lock:
            if self._pool is None:
                # «forkserver»/«spawn» y no «fork»: los procesos no heredan hilos ni el socket del servidor.
                methods = mp.get_all_start_methods()
                ctx = mp.get_context("forkserver" if "forkserver" in methods else "spawn")
                self._pool = cf.ProcessPoolExecutor(max_workers=self.workers, initializer=_worker_init,
                                                    initargs=(str(self.root), str(FONTS_DIR)), mp_context=ctx)
                self._start_reaper()
            return self._pool

    def _start_reaper(self) -> None:
        if getattr(self, "_reaper", None) is not None or IDLE_RELEASE_SECONDS <= 0:
            return

        def loop():
            while True:
                time.sleep(min(15.0, IDLE_RELEASE_SECONDS / 3))
                busy = self._busy > 0
                if self._pool is not None and not busy and time.monotonic() - self._last_use > IDLE_RELEASE_SECONDS:
                    self.shutdown()

        self._reaper = threading.Thread(target=loop, name="bp-pool-reaper", daemon=True)
        self._reaper.start()

    def busy(self):
        """Marca el grupo como en uso mientras dura una exportación (no se libera a mitad)."""
        rt = self

        class _Busy:
            def __enter__(self):
                rt._busy += 1
                rt._last_use = time.monotonic()

            def __exit__(self, *exc):
                rt._busy -= 1
                rt._last_use = time.monotonic()

        return _Busy()

    def kill_pool(self) -> None:
        """Cancelación inmediata: termina los procesos en curso y descarta el grupo."""
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is None:
            return
        procs = list(getattr(pool, "_processes", {}).values())
        pool.shutdown(wait=False, cancel_futures=True)
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass

    def shutdown(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)

    def prune(self, max_mb: int = 800) -> int:
        """Borra los fragmentos y vistas previas más antiguos si la caché supera ``max_mb``."""
        files = [p for d in (self.cache, self.base / "previews") if d.exists() for p in d.iterdir() if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        removed = 0
        while files and total > max_mb * 1024 * 1024:
            p = files.pop(0)
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
            removed += 1
        return removed

    def put_assets(self, doc: Document) -> dict[str, str]:
        mapping = {}
        for name, data in doc.assets.items():
            ext = Path(name).suffix.lower() or ".png"
            h = hashlib.sha256(data).hexdigest()[:20] + ext
            p = self.assets / h
            if not p.exists():
                p.write_bytes(data)
            mapping[name] = h
        return mapping


def default_workers() -> int:
    """Hasta 4 procesos, uno menos que los núcleos, y ~300 MB libres por proceso."""
    n = max(1, min(4, (os.cpu_count() or 2) - 1))
    try:
        free = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        n = max(1, min(n, int((free - 512 * 2**20) // (300 * 2**20))))
    except (ValueError, OSError, AttributeError):
        pass
    env = os.environ.get("BOOKPUBLISHER_WORKERS")
    return max(1, int(env)) if env and env.isdigit() else n


# ---------------------------------------------------------------- worker
_W: dict = {}


def _worker_init(root: str, fonts: str) -> None:
    import typst

    _W["root"] = root
    _W["fonts"] = typst.Fonts(include_system_fonts=False, include_embedded_fonts=True, font_paths=[fonts])


def compile_chunk(rel: str, out_pdf: str, query: bool) -> dict:
    """Compila un archivo .typ dentro de la raíz; devuelve páginas, marcas y tiempo."""
    import typst

    if "fonts" not in _W:  # llamada directa (sin grupo de procesos)
        _worker_init(os.environ.get("BP_ROOT", ""), str(FONTS_DIR))
    t0 = time.perf_counter()
    comp = typst.Compiler(str(Path(_W["root"]) / rel), root=_W["root"], font_paths=_W["fonts"],
                          ignore_system_fonts=True)
    try:
        pdf, warnings = comp.compile_with_warnings(format="pdf")
    except typst.TypstError as e:  # pragma: no cover - el mensaje depende de Typst
        return {"error": str(getattr(e, "message", e)), "hints": list(getattr(e, "hints", []) or []),
                "diagnostic": str(getattr(e, "diagnostic", "") or "")[:4000]}
    marks = {"chapters": [], "sections": []}
    if query:
        marks["chapters"] = json.loads(comp.query("<bp-chapter-page>", field="value"))
        marks["sections"] = json.loads(comp.query("<bp-section>", field="value"))
    Path(out_pdf).write_bytes(pdf)
    import pymupdf

    with pymupdf.open(out_pdf) as d:
        pages = d.page_count
    return {"pages": pages, "ms": (time.perf_counter() - t0) * 1000, "marks": marks,
            "warnings": [str(getattr(w, "message", w)) for w in (warnings or [])][:5]}


# -------------------------------------------------------------- planning
def build_chunks(doc: Document, opts: dict, writer: TypstWriter, theme_id: str, asset_map: dict) -> tuple[str, list[Chunk]]:
    meta = dict(doc.meta)
    meta["options"] = opts
    meta_lit = writer.meta_literal({"options": opts})
    head = (f'#import "/themes/_lib/common.typ": *\n'
            f'#import "/themes/{theme_id}/theme.typ" as th\n'
            f"#let meta = {meta_lit}\n"
            f"#show: th.setup.with(meta)\n"
            f"#counter(page).update(@@START@@)\n")
    mode = opts.get("chapter_break", "page")
    tail = "\n"
    groups: list[list[int]]
    if mode == "flow":
        groups = [list(range(len(doc.chapters)))] if doc.chapters else []
    else:
        groups = [[i] for i in range(len(doc.chapters))]
    dropcaps = bool(opts.get("dropcaps", True))
    chunks: list[Chunk] = []
    for gi, idxs in enumerate(groups):
        parts = []
        words = 0
        for i in idxs:
            ch = doc.chapters[i]
            parts.append(f"#context [#metadata((idx: {i}, page: here().page())) <bp-chapter-page>]")
            parts.append(writer.chapter_body(ch, drop=dropcaps))
            words += chapter_words(ch)
        src = _fix_assets(head + "\n\n".join(parts) + tail, asset_map)
        key = hashlib.sha256((themes_version() + theme_id + src).encode("utf-8")).hexdigest()[:32]
        chunks.append(Chunk(gi, idxs, src, words, key))
    return head, chunks


def _fix_assets(src: str, mapping: dict[str, str]) -> str:
    for name, hashed in mapping.items():
        src = src.replace(tstr("/assets/" + name.split("/")[-1]), tstr("/assets/" + hashed))
    return src


def front_source(doc: Document, opts: dict, writer: TypstWriter, theme_id: str, entries: list[dict],
                 asset_map: dict, with_cover: bool, with_toc: bool) -> str:
    extra = {"options": opts}
    img = doc.meta.get("cover_image")
    if img and str(img) in asset_map:
        extra["cover_image"] = "/assets/" + asset_map[str(img)]
    elif img and not str(img).startswith("/assets/"):
        extra["cover_image"] = None
    meta_lit = writer.meta_literal(extra)
    parts = [f'#import "/themes/_lib/common.typ": *',
             f'#import "/themes/{theme_id}/theme.typ" as th',
             f"#let meta = {meta_lit}"]
    if with_cover:
        parts.append("#th.cover(meta)")
    body = []
    if doc.front:
        body.append(writer.blocks(doc.front))
    if with_toc and entries:
        ent = "(" + "".join(
            f"(level: {e['level']}, label: {tstr(e['label'])}, title: {tstr(e['title'])}, page: {e['page'] or tstr('–')}),"
            for e in entries) + ")"
        if body:
            body.append("#pagebreak()")
        body.append(f"#th.toc({ent}, meta)")
    if body:
        parts.append("#show: th.setup.with(meta, front: true)\n#counter(page).update(1)\n" + "\n\n".join(body))
    return _fix_assets("\n".join(parts) + "\n", asset_map)


def toc_entries(doc: Document, chunks: list[Chunk], depth: int, fmt: str = "{kicker}: {title}") -> list[dict]:
    entries = []
    for c in chunks:
        for i in c.chapters:
            ch = doc.chapters[i]
            phys = c.chapter_pages.get(i, 1)
            title = inline_text(ch.title).strip()
            lab = toc_label(ch, doc.meta)
            if not title:
                title = chapter_label(ch, doc.meta) or ""
                lab = ""
            elif ch.kicker and lab == "—":
                title = fmt.format(kicker=ch.kicker, title=title, title_lc=title[:1].lower() + title[1:])
            elif ch.kicker and ch.kicker.lower().startswith("anexo"):
                title = f"{ch.kicker}. {title}"
            level = 2 if ch.kicker and ch.kicker.lower().startswith("anexo") else 1
            entries.append({"level": level, "label": lab, "title": title, "page": c.start + phys - 1})
            if depth >= 2 and len(c.chapters) == 1:
                for s in c.sections:
                    if s.get("level") == 2:
                        entries.append({"level": 2, "label": "", "title": s["title"], "page": c.start + int(s["page"]) - 1})
    return entries


# ---------------------------------------------------------------- export
def export_pdf(doc: Document, options: RenderOptions, out_path: str | Path, runtime: Runtime,
               progress: Progress | None = None, cancel: threading.Event | None = None) -> ExportResult:
    """Exporta ``doc`` a ``out_path``. Emite eventos de progreso y se puede cancelar con ``cancel``."""
    with runtime.busy():
        return _export(doc, options, out_path, runtime, progress, cancel)


def _export(doc: Document, options: RenderOptions, out_path: str | Path, runtime: Runtime,
            progress: Progress | None, cancel: threading.Event | None) -> ExportResult:
    t_start = time.perf_counter()
    cancel = cancel or threading.Event()
    emit = progress or (lambda e: None)
    phases: dict[str, float] = {}
    warnings: list[str] = []

    theme = get_theme(options.theme)
    if options.normalize_titles:
        normalize_titles(doc)
        fix_dialogue_dashes(doc)
    doc.number_chapters()
    opts = options.resolved()
    if not doc.chapters:
        from ..model import Chapter as _Ch
        doc.chapters = [_Ch(title=[], blocks=doc.front, numbered=False)]
        doc.front = []
    asset_map = runtime.put_assets(doc)
    writer = TypstWriter(doc, theme.id)

    t = time.perf_counter()
    seen_numbered = False
    for ch in doc.chapters:  # anexos y colofón: lo que viene sin número tras el cuerpo numerado
        ch.appendix = seen_numbered and not ch.numbered  # type: ignore[attr-defined]
        seen_numbered = seen_numbered or ch.numbered
    _, chunks = build_chunks(doc, opts, writer, theme.id, asset_map)
    phases["preparar"] = time.perf_counter() - t
    total_words = sum(c.words for c in chunks) or 1
    emit({"type": "plan", "chunks": len(chunks), "chapters": len(doc.chapters), "words": total_words,
          "theme": theme.id, "titles": [_chapter_title(doc, c) for c in chunks]})

    # Paso 1: maquetar cada fragmento (inicio en página 1) y contar páginas.
    t = time.perf_counter()
    _run_pass(chunks, runtime, emit, cancel, phase="maquetar", total_words=total_words, t0=t_start,
              starts=None, warnings=warnings)
    phases["maquetar"] = time.perf_counter() - t

    # Paso 2: con las páginas reales, recomponer los fragmentos cuyo inicio cambió (folios).
    start = 1
    recto = opts.get("chapter_break") == "recto"
    for n, c in enumerate(chunks):
        c.start = start
        c.pad = recto and c.pages % 2 == 1 and n < len(chunks) - 1  # el último no necesita relleno
        start += c.pages + (1 if c.pad else 0)
    t = time.perf_counter()
    need = [c for c in chunks if c.start != 1]
    _run_pass(need, runtime, emit, cancel, phase="foliar", total_words=sum(c.words for c in need) or 1,
              t0=t_start, starts={c.index: c.start for c in need}, warnings=warnings)
    phases["foliar"] = time.perf_counter() - t

    # Paso 3: portada e índice (ya con los números de página definitivos).
    t = time.perf_counter()
    entries = toc_entries(doc, chunks, int(opts.get("toc_depth", 1)),
                          str(opts.get("toc_kicker_format", "{kicker}: {title}"))) if options.toc else []
    front_src = front_source(doc, opts, writer, theme.id, entries, asset_map, options.cover, options.toc)
    front_pdf = None
    if options.cover or entries or doc.front:
        emit({"type": "phase", "phase": "portada", "message": "Componiendo portada e índice"})
        front_pdf = _compile_one(runtime, front_src, "front", warnings)
    phases["portada"] = time.perf_counter() - t
    _check(cancel)

    # Paso 4: unir.
    t = time.perf_counter()
    emit({"type": "phase", "phase": "unir", "message": "Uniendo y guardando el PDF"})
    pages = _merge(doc, chunks, front_pdf, runtime, Path(out_path), entries, _paper(theme),
                   recto=opts.get("chapter_break") == "recto", has_cover=options.cover)
    phases["unir"] = time.perf_counter() - t
    seconds = time.perf_counter() - t_start
    size = Path(out_path).stat().st_size
    res = ExportResult(str(out_path), pages, round(seconds, 3), size, len(doc.chapters), total_words,
                       len(chunks), sum(1 for c in chunks if c.cached), {k: round(v, 3) for k, v in phases.items()},
                       warnings[:20])
    _remember_rate(runtime, theme.id, total_words, seconds)
    emit({"type": "done", "result": res.to_json()})
    return res


def _paper(theme) -> tuple | None:
    hexc = str(theme.defaults.get("paper", "") or "")
    if len(hexc) == 7 and hexc.startswith("#"):
        return tuple(int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return None


def _chapter_title(doc: Document, c: Chunk) -> str:
    if len(c.chapters) != 1:
        return f"{len(c.chapters)} capítulos"
    ch = doc.chapters[c.chapters[0]]
    lab = chapter_label(ch, doc.meta) or ""
    title = inline_text(ch.title).strip()
    return f"{lab} · {title}" if lab and title else (title or lab or "Capítulo")


def _check(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise ExportCancelled()


def _cache_paths(runtime: Runtime, c: Chunk, start: int) -> tuple[Path, Path]:
    base = runtime.cache / f"{c.key}-{start}"
    return base.with_suffix(".pdf"), base.with_suffix(".json")


def _run_pass(chunks: list[Chunk], runtime: Runtime, emit: Progress, cancel: threading.Event, *, phase: str,
              total_words: int, t0: float, starts: dict | None, warnings: list[str]) -> None:
    if not chunks:
        return
    todo: dict = {}
    done_words = 0
    done_n = 0
    t_phase = time.perf_counter()
    rendered_words = 0

    def finish(c: Chunk, info: dict, cached: bool):
        nonlocal done_words, done_n, rendered_words
        if starts is None:
            c.pages = info["pages"]
            c.chapter_pages = {int(m["idx"]): int(m["page"]) for m in info.get("marks", {}).get("chapters", [])}
            c.sections = info.get("marks", {}).get("sections", [])
            c.cached = cached
        done_words += c.words
        done_n += 1
        if not cached:
            rendered_words += c.words
        elapsed = time.perf_counter() - t_phase
        rate = rendered_words / elapsed if rendered_words and elapsed > 0 else None
        remaining = total_words - done_words
        eta = round(remaining / rate, 1) if rate else None
        emit({"type": "chunk", "phase": phase, "index": c.index, "done": done_n, "total": len(chunks),
              "pages": info["pages"], "cached": cached, "ms": round(info.get("ms", 0)),
              "words_done": done_words, "words_total": total_words, "eta_seconds": eta,
              "elapsed": round(time.perf_counter() - t0, 2)})

    for c in chunks:
        start = starts.get(c.index, 1) if starts else 1
        pdf, meta = _cache_paths(runtime, c, start)
        if pdf.exists() and meta.exists():
            finish(c, json.loads(meta.read_text()), True)
            continue
        rel = f"work/{c.key}-{start}.typ"
        (runtime.root / rel).write_text(c.source.replace("@@START@@", str(start)), encoding="utf-8")
        todo[c.index] = (c, rel, pdf, meta, start)

    emit({"type": "phase", "phase": phase,
          "message": "Maquetando capítulos" if phase == "maquetar" else "Numerando páginas",
          "pending": len(todo), "total": len(chunks)})
    if not todo:
        return
    pool = runtime.pool
    futs = {}
    # Primero los fragmentos grandes: equilibra la carga entre procesos.
    for c, rel, pdf, meta, start in sorted(todo.values(), key=lambda x: -x[0].words):
        futs[pool.submit(compile_chunk, rel, str(pdf) + ".tmp", starts is None)] = (c, rel, pdf, meta)
    try:
        for fut in cf.as_completed(futs):
            if cancel.is_set():
                raise ExportCancelled()
            c, rel, pdf, meta = futs[fut]
            info = fut.result()
            if "error" in info:
                raise RenderError(_friendly(info["error"]), chapter=str(c.index), detail=info.get("diagnostic", ""))
            os.replace(str(pdf) + ".tmp", pdf)
            meta.write_text(json.dumps(info))
            warnings.extend(info.get("warnings", []))
            finish(c, info, False)
            try:
                (runtime.root / rel).unlink()
            except OSError:
                pass
    except ExportCancelled:
        runtime.kill_pool()
        raise
    except cf.process.BrokenProcessPool as e:
        runtime.kill_pool()
        raise RenderError("Un proceso de composición se cerró inesperadamente (¿memoria insuficiente?).") from e


def _friendly(msg: str) -> str:
    return "Typst no pudo componer este fragmento: " + msg.strip().splitlines()[0][:400]


def _compile_one(runtime: Runtime, src: str, name: str, warnings: list[str]) -> Path:
    key = hashlib.sha256((themes_version() + src).encode("utf-8")).hexdigest()[:32]
    pdf = runtime.cache / f"{name}-{key}.pdf"
    if pdf.exists():
        return pdf
    rel = f"work/{name}-{key}.typ"
    (runtime.root / rel).write_text(src, encoding="utf-8")
    info = runtime.pool.submit(compile_chunk, rel, str(pdf) + ".tmp", False).result()
    if "error" in info:
        raise RenderError(_friendly(info["error"]), chapter=name, detail=info.get("diagnostic", ""))
    os.replace(str(pdf) + ".tmp", pdf)
    warnings.extend(info.get("warnings", []))
    return pdf


def _blank(dst, rect, paper: tuple | None, at: int = -1) -> None:
    page = dst.new_page(pno=at, width=rect.width, height=rect.height)
    if paper:
        page.draw_rect(page.rect, color=None, fill=paper, overlay=False)


def _merge(doc: Document, chunks: list[Chunk], front_pdf: Path | None, runtime: Runtime, out: Path,
           entries: list[dict], paper: tuple | None = None, recto: bool = False, has_cover: bool = True) -> int:
    import pymupdf as fitz

    out.parent.mkdir(parents=True, exist_ok=True)
    dst = fitz.open()
    front_pages = 0
    if front_pdf:
        with fitz.open(front_pdf) as f:
            dst.insert_pdf(f)
            front_pages = f.page_count
            size = f[0].rect
        if recto:
            # Portada sola en recto (su vuelta en blanco) y el cuerpo empieza en impar.
            if has_cover and front_pages > 1:
                _blank(dst, size, paper, at=1)
            if dst.page_count % 2 == 1:
                _blank(dst, size, paper)
    toc = []
    for c in chunks:
        pdf, _ = _cache_paths(runtime, c, c.start)
        base = dst.page_count
        with fitz.open(pdf) as f:  # noqa: SIM117
            dst.insert_pdf(f)
            if c.pad:
                _blank(dst, f[-1].rect, paper)
        for i in c.chapters:
            ch = doc.chapters[i]
            title = inline_text(ch.title).strip()
            lab = chapter_label(ch, doc.meta)
            text = f"{lab}. {title}" if lab and title else (title or lab or "Capítulo")
            toc.append([1, text, base + c.chapter_pages.get(i, 1)])
    if front_pages:
        toc.insert(0, [1, "Portada e índice", 1])
    if toc:
        dst.set_toc(toc)
    dst.set_metadata({"title": doc.title, "author": str(doc.meta.get("author", "") or ""),
                      "creator": "BookPublisher", "producer": "BookPublisher (Typst + PyMuPDF)"})
    # Los fragmentos llegan comprimidos desde Typst; garbage=1 quita objetos huérfanos sin re-deduplicar.
    tmp = out.with_suffix(".part")
    dst.save(tmp, garbage=1, deflate=True)
    n = dst.page_count
    dst.close()
    os.replace(tmp, out)
    return n


# ----------------------------------------------------------- estimates
def _rate_file(runtime: Runtime) -> Path:
    return runtime.base / "rates.json"


def _remember_rate(runtime: Runtime, theme: str, words: int, seconds: float) -> None:
    try:
        p = _rate_file(runtime)
        data = json.loads(p.read_text()) if p.exists() else {}
        if words > 5000 and seconds > 0:
            data[theme] = round(words / seconds)
            p.write_text(json.dumps(data))
    except (OSError, ValueError):
        pass


def estimate_seconds(runtime: Runtime, theme: str, words: int) -> float:
    """Estimación antes de exportar, con la velocidad medida en exportaciones anteriores."""
    try:
        data = json.loads(_rate_file(runtime).read_text())
        rate = data.get(theme)
    except (OSError, ValueError):
        rate = None
    rate = rate or 60000  # palabras/s en primera exportación de este equipo (medido en la novela)
    return round(words / rate + 0.6, 1)
