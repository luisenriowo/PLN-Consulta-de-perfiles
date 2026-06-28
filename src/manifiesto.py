"""Manifiesto de figuras precomputadas (`data/figuras.json`).

Cada figura se procesa OFFLINE y deja sus salidas en
`data/salidas/<slug>/{b0_lead,b1_extractive,sistema_rag,ablacion}.json` y su
corpus en `data/corpus_<slug>.parquet`. El manifiesto lista las figuras YA
procesadas para poblar el selector de la app. Módulo ligero (solo json/stdlib):
la API lo importa sin arrastrar spaCy/torch.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path("data")
MANIFIESTO = DATA / "figuras.json"
CONDICIONES = ["b0_lead", "b1_extractive", "sistema_rag", "ablacion"]


def salidas_dir(slug: str) -> Path:
    return DATA / "salidas" / slug


def corpus_path(slug: str) -> Path:
    return DATA / f"corpus_{slug}.parquet"


def grafo_path(slug: str) -> Path:
    return DATA / f"graph_{slug}.duckdb"


def _resumen_figura(slug: str) -> dict | None:
    """rango_fechas y n_eventos (clusters distintos) desde las salidas de la figura."""
    fechas: set[str] = set()
    clusters: set[str] = set()
    for cond in CONDICIONES:
        ruta = salidas_dir(slug) / f"{cond}.json"
        if not ruta.exists():
            continue
        for e in json.loads(ruta.read_text(encoding="utf-8")):
            fechas.add(e["fecha"])
            if e.get("cluster_id"):
                clusters.add(e["cluster_id"])
    if not fechas:
        return None
    return {"rango_fechas": [min(fechas), max(fechas)], "n_eventos": len(clusters)}


def cargar() -> list[dict]:
    """Lista de figuras del manifiesto (vacía si no existe)."""
    if not MANIFIESTO.exists():
        return []
    return json.loads(MANIFIESTO.read_text(encoding="utf-8"))


def _persistir(figs: dict[str, dict]) -> None:
    """Escribe el manifiesto ordenado por nombre."""
    MANIFIESTO.parent.mkdir(parents=True, exist_ok=True)
    MANIFIESTO.write_text(
        json.dumps(
            sorted(figs.values(), key=lambda f: f["nombre"]),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def actualizar(slug: str, nombre: str) -> dict:
    """Inserta/actualiza la entrada de la figura en el manifiesto y la devuelve."""
    info = _resumen_figura(slug)
    if info is None:
        raise FileNotFoundError(
            f"No hay salidas para '{slug}' en {salidas_dir(slug)}/. "
            "Precomputa la figura antes de registrarla en el manifiesto."
        )
    figs = {f["slug"]: f for f in cargar()}
    figs[slug] = {"slug": slug, "nombre": nombre, "tipo": "figura", **info}
    _persistir(figs)
    return figs[slug]


def actualizar_tema(
    slug: str,
    nombre: str,
    *,
    n_entidades: int,
    n_relaciones: int,
    rango_fechas: list[str] | None,
) -> dict:
    """Inserta/actualiza la entrada de un TEMA en el manifiesto y la devuelve.

    Un tema no tiene salidas de las 4 condiciones; su resumen viene del grafo
    (nº de entidades, nº de relaciones y rango de fechas de las aristas).
    """
    figs = {f["slug"]: f for f in cargar()}
    figs[slug] = {
        "slug": slug,
        "nombre": nombre,
        "tipo": "tema",
        "rango_fechas": rango_fechas,
        "n_entidades": n_entidades,
        "n_relaciones": n_relaciones,
    }
    _persistir(figs)
    return figs[slug]
