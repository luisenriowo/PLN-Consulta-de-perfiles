"""Producto — Backend FastAPI (OBLIGATORIO, CLAUDE.md §9).

Sirve la línea de tiempo generada (JSON) por condición, con las fuentes
resueltas a URLs para la atribución. Lee las salidas precomputadas por
`scripts/run_generation.py` (data/salidas/<cond>.json) y el mapa doc_id→url del
corpus. No sobre-ingenierizar: expone lo justo para el frontend.

Levantar:  uvicorn src.app.api:app --reload
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException

from src.assemble import assemble
from src.schemas import TimelineEntry

SALIDAS = Path("data/salidas")
CORPUS = Path("data/corpus_humala.parquet")
SUJETO = "Ollanta Humala"

app = FastAPI(title="timeline-gen", description="Líneas de tiempo de figuras políticas")


@lru_cache(maxsize=1)
def _mapa_urls() -> dict[str, str]:
    """doc_id -> url, para resolver las fuentes de cada entrada."""
    if not CORPUS.exists():
        return {}
    df = pd.read_parquet(CORPUS, columns=["doc_id", "url"])
    return dict(zip(df["doc_id"], df["url"]))


def _condiciones() -> list[str]:
    return sorted(p.stem for p in SALIDAS.glob("*.json")) if SALIDAS.exists() else []


def _cargar(cond: str) -> list[TimelineEntry]:
    ruta = SALIDAS / f"{cond}.json"
    if not ruta.exists():
        raise HTTPException(404, f"condición '{cond}' no encontrada")
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    entries = [
        TimelineEntry(
            fecha=date.fromisoformat(e["fecha"]),
            resumen=e["resumen"],
            fuentes=e.get("fuentes", []),
            confianza=e.get("confianza"),
        )
        for e in crudo
    ]
    return assemble(entries)


@app.get("/")
def raiz() -> dict:
    return {"sujeto": SUJETO, "condiciones": _condiciones()}


@app.get("/condiciones")
def condiciones() -> list[str]:
    return _condiciones()


@app.get("/timeline/{cond}")
def timeline(cond: str) -> dict:
    """Línea de tiempo de la condición, con fuentes resueltas a URLs."""
    urls = _mapa_urls()
    entradas = []
    for e in _cargar(cond):
        entradas.append({
            "fecha": e.fecha.isoformat(),
            "resumen": e.resumen,
            "confianza": e.confianza,
            "fuentes": [{"doc_id": f, "url": urls.get(f, "")} for f in e.fuentes],
        })
    return {"sujeto": SUJETO, "condicion": cond, "entradas": entradas}
