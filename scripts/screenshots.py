"""Recorre el estudio con Playwright y guarda capturas en docs/screenshots.

Requisitos: el servidor corriendo (``bookpublisher serve``) con la web compilada,
``pip install playwright`` y un Chrome/Chromium. Solo usa textos de muestra
(dominio público o escritos para el proyecto).

    python scripts/screenshots.py --url http://127.0.0.1:8765 \
        --long /tmp/quijote-completo.md --pdf /tmp/codice-ejemplo.pdf
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--long", help="libro largo para la captura de progreso (p. ej. el Quijote completo)")
    ap.add_argument("--pdf", help="PDF de muestra para la captura de importación")
    ap.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chromium"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(a.url)
        page.evaluate("localStorage.clear()")
        page.reload()
        page.wait_for_selector(".theme")
        page.screenshot(path=OUT / "01-bienvenida.png")

        def open_doc(path: Path) -> None:
            if page.locator(".doc-card").count():
                page.locator(".rail label.btn input[type=file]").set_input_files(str(path))
            else:
                page.locator(".drop input[type=file]").set_input_files(str(path))
            page.wait_for_function(f"document.querySelector('.doc-card')?.textContent.includes('{path.name}')")

        def wait_preview() -> None:
            page.wait_for_timeout(400)
            page.wait_for_function("!document.querySelector('.pages.loading') && document.querySelectorAll('.page img').length > 0")
            page.wait_for_function("[...document.querySelectorAll('.page img')].every(i => i.complete && i.naturalWidth > 0)")

        def pick_theme(name: str) -> None:
            page.locator(".theme", has_text=name).click()

        # Novela clásica
        open_doc(ROOT / "samples" / "quijote-ejemplo.md")
        pick_theme("Novela clásica")
        wait_preview()
        page.screenshot(path=OUT / "02-novela-portada.png")
        page.locator(".chapters button").nth(3).click()
        wait_preview()
        page.screenshot(path=OUT / "03-novela-capitulo.png")

        # Códice
        open_doc(ROOT / "samples" / "codice-ejemplo.md")
        pick_theme("Códice")
        page.locator(".chapters button").nth(2).click()
        wait_preview()
        page.screenshot(path=OUT / "04-codice.png")

        # Manual técnico
        open_doc(ROOT / "samples" / "guia-formato.md")
        pick_theme("Manual técnico")
        page.locator(".chapters button").nth(3).click()
        wait_preview()
        page.screenshot(path=OUT / "05-manual.png")

        # Libro largo: progreso de exportación y resultado
        if a.long:
            open_doc(Path(a.long))
            pick_theme("Novela clásica")
            wait_preview()
            page.get_by_role("button", name="Exportar PDF").click()
            page.wait_for_function("(() => { const i = document.querySelector('.bar i'); return i && parseFloat(i.style.width) > 25; })()",
                                   polling=50, timeout=60000)
            page.screenshot(path=OUT / "06-exportando.png")
            page.wait_for_selector(".export[data-status=done]", timeout=120000)
            page.screenshot(path=OUT / "07-exportado.png")
            # Cancelación: cambiar el cuerpo invalida la caché, exportar y cancelar enseguida.
            page.locator(".field input[type=number]").fill("10")
            page.locator(".field input[type=number]").press("Tab")
            page.locator(".export .close").click()
            page.get_by_role("button", name="Exportar PDF").click()
            page.wait_for_function("(() => { const i = document.querySelector('.bar i'); return i && parseFloat(i.style.width) > 2; })()",
                                   polling=20, timeout=60000)
            t = time.time()
            page.keyboard.press("Escape")
            page.wait_for_selector(".export[data-status=cancelled]", timeout=20000)
            print(f"cancelación confirmada en {time.time() - t:.2f} s")

        # Importar PDF
        if a.pdf:
            page.get_by_role("link", name="Importar PDF").click()
            page.locator(".drop input[type=file]").set_input_files(a.pdf)
            page.wait_for_selector(".progress[data-status=done]", timeout=120000)
            page.screenshot(path=OUT / "08-importar.png", full_page=True)
            page.get_by_role("button", name="Abrir en el estudio").click()
            wait_preview()
            page.screenshot(path=OUT / "09-importado-en-estudio.png")
        browser.close()
    print("errores de consola:", errors or "ninguno")
    for f in sorted(OUT.glob("*.png")):
        print(f)


if __name__ == "__main__":
    main()
