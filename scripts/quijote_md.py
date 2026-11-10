"""Convierte «Don Quijote» (dominio público, Proyecto Gutenberg #2000) a Markdown.

Sirve como muestra larga para pruebas de rendimiento sin usar textos privados:

    python scripts/quijote_md.py --chapters 8 > samples/quijote-ejemplo.md
    python scripts/quijote_md.py > /tmp/quijote-completo.md     # ~380 000 palabras

Si no se pasa --src, descarga el texto de gutenberg.org.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request

URL = "https://www.gutenberg.org/cache/epub/2000/pg2000.txt"
CAP = re.compile(r"^Capítulo (primero|[IVXLC]+)\.\s*(.*)$")
PART = re.compile(r"^(Primera|Segunda) parte del ingenioso (hidalgo|caballero) don Quijote de la Mancha$")


def convert(text: str, max_chapters: int | None = None) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    start = next(i for i, l in enumerate(lines) if CAP.match(l))
    end = next((i for i, l in enumerate(lines) if l.startswith("*** END OF")), len(lines))
    out = ["---", "title: El ingenioso hidalgo don Quijote de la Mancha", "author: Miguel de Cervantes Saavedra",
           "lang: es", "description: Texto de dominio público (Proyecto Gutenberg n.º 2000).", "---", ""]
    paras: list[str] = []
    buf: list[str] = []
    chapters = 0
    i = start
    while i < end:
        line = lines[i].rstrip()
        m = CAP.match(line)
        if m and not buf:
            title = m.group(2)
            j = i + 1
            while j < end and lines[j].strip():
                title += " " + lines[j].strip()
                j += 1
            chapters += 1
            if max_chapters and chapters > max_chapters:
                break
            n = chapters
            paras.append(f"# Capítulo {n}: {title.strip()}")
            i = j
            continue
        if PART.match(line.strip()):
            i += 1
            continue
        if line.strip():
            buf.append(line.strip())
        elif buf:
            paras.append(_clean(" ".join(buf)))
            buf = []
        i += 1
    if buf:
        paras.append(_clean(" ".join(buf)))
    return "\n".join(out) + "\n\n".join(paras) + "\n"


def _clean(p: str) -> str:
    p = re.sub(r"''(.+?)''", r"«\1»", p)
    p = re.sub(r"\s+", " ", p)
    p = re.sub(r"_(.+?)_", r"*\1*", p)
    return p.replace("[", "\\[").replace("]", "\\]")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chapters", type=int, default=None)
    ap.add_argument("--src", help="ruta local a pg2000.txt")
    a = ap.parse_args()
    if a.src:
        text = open(a.src, encoding="utf-8").read()
    else:
        text = urllib.request.urlopen(URL, timeout=60).read().decode("utf-8")
    sys.stdout.write(convert(text, a.chapters))


if __name__ == "__main__":
    main()
