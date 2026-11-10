"""API local del estudio.

Escucha solo en 127.0.0.1 por defecto: los textos no salen de la máquina.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import threading
import time
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..model import Document, chapter_words, inline_text
from ..readers import read_any
from ..render.pipeline import RenderError, RenderOptions, Runtime, estimate_seconds, export_pdf
from ..render.preview import preview
from ..themes import all_themes
from ..writers.typst_writer import chapter_label
from .jobs import Job, JobManager

MAX_UPLOAD = 200 * 1024 * 1024
TEXT_EXT = {".md", ".markdown", ".txt", ".docx"}


class ExportOptions(BaseModel):
    theme: str = "novela"
    page_size: str | None = None
    font_size: float | None = Field(default=None, ge=7, le=16)
    chapter_break: str | None = Field(default=None, pattern="^(flow|page|recto)$")
    dropcaps: bool | None = None
    hyphenate: bool = True
    toc: bool = True
    cover: bool = True
    title: str | None = None
    author: str | None = None

    def render(self) -> RenderOptions:
        return RenderOptions(theme=self.theme, page_size=self.page_size, font_size=self.font_size,
                             chapter_break=self.chapter_break, dropcaps=self.dropcaps, hyphenate=self.hyphenate,
                             toc=self.toc, cover=self.cover)


class ExportRequest(BaseModel):
    document: str
    format: str = Field(default="pdf", pattern="^(pdf|docx|md)$")
    options: ExportOptions = ExportOptions()


class Store:
    """Documentos abiertos en el estudio (en memoria, con su origen en disco)."""

    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self.dir = runtime.base / "documents"
        self.out = runtime.base / "outputs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self.docs: dict[str, dict] = {}

    def add(self, name: str, raw: bytes | None, doc: Document | None = None) -> dict:
        did = uuid.uuid4().hex[:12]
        t = time.perf_counter()
        if doc is None:
            doc = read_any(name, raw)
        entry = {"id": did, "name": name, "raw": raw, "doc": doc, "parse_seconds": round(time.perf_counter() - t, 3),
                 "created": time.time()}
        self.docs[did] = entry
        while len(self.docs) > 12:  # memoria acotada: se descartan los documentos más antiguos
            oldest = min(self.docs, key=lambda k: self.docs[k]["created"])
            self.docs.pop(oldest)
        return entry

    def fresh(self, did: str) -> Document:
        """Copia del documento (la exportación normaliza títulos sobre el objeto)."""
        e = self.get(did)
        if e["raw"] is not None:
            return read_any(e["name"], e["raw"])
        import copy
        return copy.deepcopy(e["doc"])

    def get(self, did: str) -> dict:
        e = self.docs.get(did)
        if not e:
            raise HTTPException(404, "Documento no encontrado (¿se reinició el servidor?). Vuelve a abrirlo.")
        return e


def outline(entry: dict, runtime: Runtime) -> dict:
    doc: Document = entry["doc"]
    import copy

    from ..render.normalize import normalize_titles
    d = copy.deepcopy(doc)
    normalize_titles(d)
    d.number_chapters()
    chapters = []
    for i, ch in enumerate(d.chapters):
        chapters.append({"index": i, "label": chapter_label(ch, d.meta) or "", "title": inline_text(ch.title).strip(),
                         "words": chapter_words(ch), "numbered": ch.numbered})
    words = sum(c["words"] for c in chapters)
    estimates = {tid: estimate_seconds(runtime, tid, words) for tid in all_themes()}
    meta = {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in d.meta.items()
            if k in ("title", "subtitle", "author", "kicker", "edition", "lang")}
    return {"id": entry["id"], "name": entry["name"], "meta": meta, "title": d.title, "chapters": chapters,
            "words": words, "front_blocks": len(d.front), "images": len(d.assets),
            "parse_seconds": entry["parse_seconds"], "estimates": estimates}


def safe_name(name: str, fallback: str = "documento") -> str:
    stem = Path(name or fallback).stem
    stem = re.sub(r"[^\w\-. áéíóúñÁÉÍÓÚÑüÜ]+", "", stem).strip(" .") or fallback
    return stem[:80]


def create_app(runtime: Runtime | None = None, static_dir: Path | None = None) -> FastAPI:
    runtime = runtime or Runtime()
    store = Store(runtime)
    jobs = JobManager()
    app = FastAPI(title="BookPublisher", version=__version__)
    app.state.runtime, app.state.store, app.state.jobs = runtime, store, jobs

    # ------------------------------------------------------------- básicos
    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "workers": runtime.workers}

    @app.get("/api/themes")
    def themes():
        return [t.to_json() for t in all_themes().values()]

    # ---------------------------------------------------------- documentos
    @app.post("/api/documents")
    async def open_document(file: UploadFile | None = File(default=None), text: str | None = Form(default=None),
                            name: str | None = Form(default=None)):
        if file is not None:
            fname = file.filename or "documento.md"
            ext = Path(fname).suffix.lower()
            if ext == ".pdf":
                raise HTTPException(415, "Para PDF usa «Importar PDF»: lo convierte a Markdown o Word.")
            if ext not in TEXT_EXT:
                raise HTTPException(415, f"Formato no soportado ({ext or 'sin extensión'}). Usa .md, .txt o .docx.")
            raw = await file.read(MAX_UPLOAD + 1)
            if len(raw) > MAX_UPLOAD:
                raise HTTPException(413, "El archivo supera los 200 MB.")
        elif text:
            fname = (safe_name(name or "texto") + ".md")
            raw = text.encode("utf-8")
        else:
            raise HTTPException(400, "Envía un archivo o un texto.")
        try:
            entry = await asyncio.to_thread(store.add, fname, raw)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return outline(entry, runtime)

    @app.get("/api/documents/{did}")
    def get_document(did: str):
        return outline(store.get(did), runtime)

    @app.delete("/api/documents/{did}")
    def close_document(did: str):
        store.docs.pop(did, None)
        return {"ok": True}

    @app.post("/api/documents/{did}/preview")
    async def preview_document(did: str, opts: ExportOptions, target: str = "0", pages: int = 4):
        store.get(did)
        doc = store.fresh(did)
        _apply_meta(doc, opts)
        tgt: str | int = "cover" if target == "cover" else int(target)
        t = time.perf_counter()
        try:
            res = await asyncio.to_thread(preview, doc, opts.render(), runtime, tgt, max(1, min(pages, 8)), 110)
        except RenderError as e:
            return JSONResponse({"error": str(e), "detail": e.detail[:2000]}, status_code=422)
        except KeyError as e:
            raise HTTPException(400, f"Tema desconocido: {e}") from e
        for p in res["pages"]:
            p["url"] = f"/api/previews/{p['key']}.png"
            p.pop("png", None)
        res["seconds"] = round(time.perf_counter() - t, 3)
        return res

    @app.get("/api/previews/{key}.png")
    def preview_png(key: str):
        if not re.fullmatch(r"[0-9a-f]{24}", key):
            raise HTTPException(404)
        p = runtime.base / "previews" / f"{key}.png"
        if not p.exists():
            raise HTTPException(404)
        return FileResponse(p, media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    # ------------------------------------------------------------ exportar
    @app.post("/api/exports")
    def start_export(req: ExportRequest):
        entry = store.get(req.document)
        if req.options.theme not in all_themes():
            raise HTTPException(400, f"Tema desconocido: {req.options.theme}")
        base = safe_name(entry["name"])

        def work(job: Job):
            doc = store.fresh(req.document)
            _apply_meta(doc, req.options)
            out_dir = store.out / job.id
            out_dir.mkdir(parents=True, exist_ok=True)
            if req.format == "pdf":
                out = out_dir / f"{base}.pdf"
                def emit(ev: dict) -> None:  # sin rutas del servidor en los eventos
                    if ev.get("type") == "done":
                        ev = {**ev, "result": {**ev["result"], "path": None}}
                    job.emit(ev)

                res = export_pdf(doc, req.options.render(), out, runtime, progress=emit, cancel=job.cancel)
                job.result = res.to_json() | {"path": None, "file": out.name}
                job.files["pdf"] = str(out)
            elif req.format == "docx":
                from ..writers.docx_writer import write_docx
                job.emit({"type": "phase", "phase": "docx", "message": "Escribiendo Word"})
                out = out_dir / f"{base}.docx"
                t = time.perf_counter()
                write_docx(doc, out)
                job.result = {"file": out.name, "seconds": round(time.perf_counter() - t, 3), "size_bytes": out.stat().st_size}
                job.files["docx"] = str(out)
            else:
                out = _md_zip(doc, out_dir, base)
                job.result = {"file": out.name, "size_bytes": out.stat().st_size}
                job.files["md"] = str(out)
            job.status = "done"
            job.emit({"type": "finished", "result": job.result})
            runtime.prune()

        job = jobs.submit("export", f"{base}.{req.format}", work)
        return job.summary()

    # ------------------------------------------------------------ importar
    @app.post("/api/imports")
    async def start_import(file: UploadFile = File(...), images: bool = Form(default=True),
                           tables: bool = Form(default=True)):
        fname = file.filename or "documento.pdf"
        if Path(fname).suffix.lower() != ".pdf":
            raise HTTPException(415, "Solo se importan PDF. Los .md, .txt y .docx se abren directamente en el estudio.")
        raw = await file.read(MAX_UPLOAD + 1)
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "El archivo supera los 200 MB.")
        if not raw.startswith(b"%PDF"):
            raise HTTPException(415, "El archivo no es un PDF.")
        base = safe_name(fname)

        def work(job: Job):
            from ..readers.pdf_reader import read_pdf
            from ..writers.docx_writer import write_docx
            out_dir = store.out / job.id
            out_dir.mkdir(parents=True, exist_ok=True)
            src = out_dir / "origen.pdf"
            src.write_bytes(raw)
            t = time.perf_counter()
            job.emit({"type": "phase", "phase": "leer", "message": "Leyendo páginas"})
            doc, report = read_pdf(str(src), progress=job.emit, cancel=job.cancel, with_images=images, with_tables=tables)
            t_read = time.perf_counter() - t
            src.unlink(missing_ok=True)
            words = sum(chapter_words(c) for c in doc.chapters) + sum(chapter_words(_wrap(doc.front)) for _ in [0])
            if words < 5:
                raise ValueError("El PDF no tiene texto seleccionable (¿es un escaneo?). BookPublisher no hace OCR.")
            job.emit({"type": "phase", "phase": "escribir", "message": "Escribiendo Markdown y Word"})
            md_zip = _md_zip(doc, out_dir, base)
            docx = out_dir / f"{base}.docx"
            write_docx(doc, docx)
            entry = store.add(f"{base}.md", None, doc)
            job.files.update({"md": str(md_zip), "docx": str(docx)})
            job.result = {"report": asdict(report), "words": words, "chapters": len(doc.chapters),
                          "seconds": round(time.perf_counter() - t, 3), "read_seconds": round(t_read, 3),
                          "document": entry["id"], "title": doc.title,
                          "markdown_preview": _md_head(doc)}
            job.status = "done"
            job.emit({"type": "finished", "result": job.result})

        job = jobs.submit("import", fname, work)
        return job.summary()

    # -------------------------------------------------------------- trabajos
    @app.get("/api/jobs")
    def list_jobs():
        return [j.summary() for j in sorted(jobs.jobs.values(), key=lambda j: -j.created)]

    @app.get("/api/jobs/{jid}")
    def job_status(jid: str):
        return _job(jobs, jid).summary()

    @app.post("/api/jobs/{jid}/cancel")
    def cancel_job(jid: str):
        job = _job(jobs, jid)
        job.cancel.set()
        if job.kind == "export" and job.status == "running":
            threading.Thread(target=runtime.kill_pool, daemon=True).start()
        return {"ok": True}

    @app.get("/api/jobs/{jid}/events")
    async def job_events(jid: str, request: Request):
        job = _job(jobs, jid)
        start = int(request.headers.get("last-event-id", -1)) + 1

        async def stream():
            i = start
            yield "retry: 1500\n\n"
            while True:
                if await request.is_disconnected():
                    return
                evs = job.events[i:]
                for ev in evs:
                    yield f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                i += len(evs)
                if job.status in ("done", "error", "cancelled") and i >= len(job.events):
                    yield "event: end\ndata: {}\n\n"
                    return
                if not evs:
                    await asyncio.to_thread(_wait, job, i, 10.0)
                    if i >= len(job.events):
                        yield ": ping\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/jobs/{jid}/files/{kind}")
    def job_file(jid: str, kind: str, inline: bool = False):
        job = _job(jobs, jid)
        path = job.files.get(kind)
        if not path or not Path(path).exists():
            raise HTTPException(404, "Archivo no disponible.")
        media = {"pdf": "application/pdf", "md": "application/zip",
                 "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[kind]
        p = Path(path)
        return FileResponse(p, media_type=media, filename=p.name,
                            content_disposition_type="inline" if inline else "attachment")

    # ------------------------------------------------------ estudio (Angular)
    static_dir = static_dir or _default_static()
    if static_dir and (static_dir / "index.html").exists():
        @app.get("/{path:path}")
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = (static_dir / path).resolve()
            if path and f.is_file() and static_dir.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(static_dir / "index.html")

    return app


# ------------------------------------------------------------------ helpers
def _apply_meta(doc: Document, opts: ExportOptions) -> None:
    if opts.title:
        doc.meta["title"] = opts.title
    if opts.author:
        doc.meta["author"] = opts.author


def _job(jobs: JobManager, jid: str) -> Job:
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Trabajo no encontrado.")
    return job


def _wait(job: Job, seen: int, timeout: float) -> None:
    with job.cond:
        if len(job.events) <= seen and job.status not in ("done", "error", "cancelled"):
            job.cond.wait(timeout)


def _wrap(blocks):
    from ..model import Chapter
    return Chapter(title=[], blocks=blocks)


def _md_zip(doc: Document, out_dir: Path, base: str) -> Path:
    from ..writers import save_markdown_bundle
    tmp = out_dir / "md"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    md = tmp / f"{base}.md"
    files = save_markdown_bundle(doc, md)
    if len(files) <= 1:  # sin imágenes: el .md suelto
        dst = out_dir / md.name
        shutil.move(str(md), dst)
        shutil.rmtree(tmp)
        return dst
    z = out_dir / f"{base}-markdown.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(tmp))
    shutil.rmtree(tmp)
    return z


def _md_head(doc: Document, limit: int = 6000) -> str:
    from ..writers.markdown_writer import write_markdown
    return write_markdown(doc)[:limit]


def _default_static() -> Path | None:
    here = Path(__file__).resolve()
    for p in [here.parents[4] / "web" / "dist" / "web" / "browser", here.parent / "static"]:
        if (p / "index.html").exists():
            return p
    return None
