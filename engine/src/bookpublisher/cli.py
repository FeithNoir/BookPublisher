"""Línea de órdenes: ``bookpublisher serve | export | import | themes``."""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path


def _bar(ev: dict, state: dict) -> None:
    t = ev.get("type")
    if t == "plan":
        print(f"  {ev['chapters']} capítulos · {ev['words']:,} palabras · tema {ev['theme']}".replace(",", "."))
    elif t == "phase":
        print(f"  · {ev.get('message', ev.get('phase'))}")
    elif t == "chunk":
        eta = ev.get("eta_seconds")
        msg = f"\r    {ev['phase']}: {ev['done']}/{ev['total']}" + (f" · quedan ~{eta:.0f} s" if eta else "") + "   "
        sys.stderr.write(msg)
        if ev["done"] == ev["total"]:
            sys.stderr.write("\n")
    elif t == "page" and ev["done"] % 10 == 0:
        sys.stderr.write(f"\r    página {ev['done']}/{ev['total']}   ")


def cmd_export(a) -> int:
    from .readers import read_any
    from .render.pipeline import ExportCancelled, RenderError, RenderOptions, Runtime, export_pdf

    t = time.perf_counter()
    doc = read_any(a.input)
    if a.title:
        doc.meta["title"] = a.title
    if a.author:
        doc.meta["author"] = a.author
    out = Path(a.output or Path(a.input).with_suffix("." + a.format))
    print(f"Leído {a.input} en {time.perf_counter() - t:.2f} s")
    if a.format == "docx":
        from .writers.docx_writer import write_docx
        write_docx(doc, out)
        print(f"Listo: {out}")
        return 0
    if a.format == "md":
        from .writers import save_markdown_bundle
        save_markdown_bundle(doc, out)
        print(f"Listo: {out}")
        return 0
    rt = Runtime(workers=a.workers)
    cancel = threading.Event()
    state: dict = {}
    try:
        res = export_pdf(doc, RenderOptions(theme=a.theme, page_size=a.page_size, font_size=a.font_size,
                                            chapter_break=a.chapter_break, toc=not a.no_toc, cover=not a.no_cover,
                                            hyphenate=not a.no_hyphenate),
                         out, rt, progress=lambda e: _bar(e, state), cancel=cancel)
    except KeyboardInterrupt:
        cancel.set()
        rt.kill_pool()
        print("\nCancelado.")
        return 130
    except (RenderError, ExportCancelled) as e:
        print(f"\nError: {e}\n{getattr(e, 'detail', '')}", file=sys.stderr)
        return 1
    finally:
        rt.shutdown()
    print(f"Listo: {out} · {res.pages} páginas · {res.seconds:.2f} s · "
          f"{res.size_bytes / 1e6:.1f} MB · {res.cached_chunks}/{res.chunks} capítulos desde caché")
    return 0


def cmd_import(a) -> int:
    from .readers.pdf_reader import read_pdf
    from .writers import save_markdown_bundle
    from .writers.docx_writer import write_docx

    t = time.perf_counter()
    doc, rep = read_pdf(a.input, progress=lambda e: _bar(e, {}), with_images=not a.no_images)
    sys.stderr.write("\n")
    base = Path(a.output or Path(a.input).with_suffix(""))
    if a.to in ("md", "ambos"):
        md = base.with_suffix(".md")
        save_markdown_bundle(doc, md)
        print(f"Markdown: {md}")
    if a.to in ("docx", "ambos"):
        dx = base.with_suffix(".docx")
        write_docx(doc, dx)
        print(f"Word: {dx}")
    print(f"{rep.pages} páginas · {len(doc.chapters)} capítulos · {rep.tables} tablas · {rep.images} imágenes · "
          f"{len(rep.removed_headers)} cabeceras/pies quitados · {rep.joined_hyphens} guiones unidos · "
          f"{time.perf_counter() - t:.2f} s")
    return 0


def cmd_themes(a) -> int:
    from .themes import all_themes
    for t in all_themes().values():
        print(f"{t.id:10} {t.name:18} {t.description}")
    return 0


def cmd_serve(a) -> int:
    import uvicorn
    from .server.app import create_app

    if a.host not in ("127.0.0.1", "localhost") and not a.allow_remote:
        print("Por seguridad el estudio solo escucha en esta máquina. Usa --allow-remote si de verdad lo quieres.")
        return 2
    print(f"BookPublisher en http://{a.host}:{a.port}")
    uvicorn.run(create_app(), host=a.host, port=a.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bookpublisher", description="Maquetación de libros: PDF ↔ Markdown/Word y exportación a PDF con temas.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="abre el estudio web")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--allow-remote", action="store_true")
    s.set_defaults(fn=cmd_serve)
    e = sub.add_parser("export", help="exporta .md/.txt/.docx a PDF (o a DOCX/MD)")
    e.add_argument("input")
    e.add_argument("-o", "--output")
    e.add_argument("-t", "--theme", default="novela")
    e.add_argument("-f", "--format", choices=["pdf", "docx", "md"], default="pdf")
    e.add_argument("--page-size")
    e.add_argument("--font-size", type=float)
    e.add_argument("--chapter-break", choices=["flow", "page", "recto"])
    e.add_argument("--title")
    e.add_argument("--author")
    e.add_argument("--no-toc", action="store_true")
    e.add_argument("--no-cover", action="store_true")
    e.add_argument("--no-hyphenate", action="store_true")
    e.add_argument("--workers", type=int)
    e.set_defaults(fn=cmd_export)
    i = sub.add_parser("import", help="convierte un PDF a Markdown y/o Word")
    i.add_argument("input")
    i.add_argument("-o", "--output", help="ruta base de salida (sin extensión)")
    i.add_argument("--to", choices=["md", "docx", "ambos"], default="ambos")
    i.add_argument("--no-images", action="store_true")
    i.set_defaults(fn=cmd_import)
    t = sub.add_parser("themes", help="lista los temas")
    t.set_defaults(fn=cmd_themes)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
