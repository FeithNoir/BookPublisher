"""Mide una exportación: tiempo por fase, páginas, tamaño y memoria (proceso principal + trabajadores).

    python scripts/benchmark.py libro.md --theme novela --out /tmp/libro.pdf [--warm]

La memoria se muestrea cada 50 ms con psutil sumando el RSS de todo el árbol de procesos.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

import psutil

from bookpublisher.readers import read_any
from bookpublisher.render.pipeline import RenderOptions, Runtime, export_pdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--theme", default="novela")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--warm", action="store_true", help="repite la exportación con la caché caliente")
    a = ap.parse_args()
    cache = Path(tempfile.mkdtemp(prefix="bp-bench-"))
    out = Path(a.out or cache / "out.pdf")
    me = psutil.Process()
    peak = {"main": 0, "workers": 0, "total": 0}
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            try:
                main = me.memory_info().rss
                kids = sum(c.memory_info().rss for c in me.children(recursive=True))
            except psutil.Error:
                continue
            peak["main"] = max(peak["main"], main)
            peak["workers"] = max(peak["workers"], kids)
            peak["total"] = max(peak["total"], main + kids)
            time.sleep(0.05)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    t = time.perf_counter()
    doc = read_any(a.input)
    parse = time.perf_counter() - t
    rt = Runtime(base=cache, workers=a.workers)
    runs = []
    try:
        for label in (["frío", "caliente"] if a.warm else ["frío"]):
            d = read_any(a.input)
            r = export_pdf(d, RenderOptions(theme=a.theme), out, rt)
            runs.append({"caché": label, **{k: v for k, v in r.to_json().items() if k not in ("path", "warnings")}})
    finally:
        stop.set()
        rt.shutdown()
        shutil.rmtree(cache, ignore_errors=True)
    mb = lambda b: round(b / 1048576)  # noqa: E731
    print(json.dumps({"archivo": Path(a.input).name, "tema": a.theme, "trabajadores": rt.workers,
                      "lectura_s": round(parse, 3), "exportaciones": runs,
                      "memoria_pico_mb": {k: mb(v) for k, v in peak.items()}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
