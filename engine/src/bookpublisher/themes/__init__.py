"""Registro de temas. Cada tema es una carpeta con ``theme.typ`` y ``theme.json``."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

THEMES_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    description: str
    defaults: dict = field(default_factory=dict)
    swatch: tuple = ()

    @property
    def path(self) -> Path:
        return THEMES_DIR / self.id

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description,
                "defaults": self.defaults, "swatch": list(self.swatch)}


@lru_cache(maxsize=1)
def all_themes() -> dict[str, Theme]:
    out: dict[str, Theme] = {}
    for d in sorted(THEMES_DIR.iterdir()):
        cfg = d / "theme.json"
        if d.is_dir() and cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            out[d.name] = Theme(d.name, data["name"], data.get("description", ""),
                                data.get("defaults", {}), tuple(data.get("swatch", [])))
    order = ["codice", "novela", "manual", "sencillo"]
    return dict(sorted(out.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))


def get_theme(theme_id: str) -> Theme:
    themes = all_themes()
    if theme_id not in themes:
        raise KeyError(f"Tema desconocido: {theme_id!r}. Disponibles: {', '.join(themes)}")
    return themes[theme_id]


@lru_cache(maxsize=1)
def themes_version() -> str:
    """Huella de todos los .typ: si cambia un tema, la caché de fragmentos se invalida."""
    h = hashlib.sha256()
    for p in sorted(THEMES_DIR.rglob("*.typ")):
        h.update(p.relative_to(THEMES_DIR).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]
