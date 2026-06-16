"""Producto — Backend FastAPI multi-figura (OBLIGATORIO, CLAUDE.md §9).

READ-ONLY sobre outputs ya precomputados. Lee `data/figuras.json` (manifiesto)
y, por figura, las salidas `data/salidas/<slug>/<cond>.json` + el corpus
`data/corpus_<slug>.parquet`. Alinea las 4 condiciones por `cluster_id`
server-side y resuelve cada fuente a {url, título, lead}. NO ejecuta el pipeline
ni llama al LLM en el request (eso es offline; ver scripts/precompute_figura.py).

Sirve además el frontend estático en `src/app/web/`.

Levantar:  uvicorn src.app.api:app --reload    →    http://127.0.0.1:8000
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import manifiesto
from src.app import jobs
from src.app import resumen as resumen_mod

WEB = Path(__file__).parent / "web"
GOLD_PROCESAL = Path("annotation/gold")
# Orden de presentación de condiciones: Sistema primero (la salida "buena").
CONDS_ORDEN = ["sistema_rag", "b1_extractive", "b0_lead", "ablacion"]

app = FastAPI(title="timeline-gen", description="Líneas de tiempo de figuras políticas")


@lru_cache(maxsize=16)
def _fuentes_map_cached(slug: str, _mtime: float) -> dict[str, dict]:
    """doc_id -> {url, titulo, lead}. `_mtime` está en la clave de caché para que
    se invalide sola al reescribir el parquet (p. ej. tras re-precomputar)."""
    corpus = manifiesto.corpus_path(slug)
    if not corpus.exists():
        return {}
    df = pd.read_parquet(corpus, columns=["doc_id", "url", "texto"])
    mapa: dict[str, dict] = {}
    for r in df.itertuples():
        lineas = str(r.texto).split("\n")
        mapa[r.doc_id] = {
            "url": r.url,
            "titulo": lineas[0] if lineas else "",
            "lead": lineas[1] if len(lineas) > 1 else "",
        }
    return mapa


def _fuentes_map(slug: str) -> dict[str, dict]:
    corpus = manifiesto.corpus_path(slug)
    mtime = corpus.stat().st_mtime if corpus.exists() else 0.0
    return _fuentes_map_cached(slug, mtime)


def _cargar_cond(slug: str, cond: str) -> list[dict]:
    ruta = manifiesto.salidas_dir(slug) / f"{cond}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []


@app.get("/api/figuras")
def figuras() -> list[dict]:
    """Manifiesto: figuras ya procesadas (para el selector)."""
    return manifiesto.cargar()


def _eventos_figura(slug: str) -> dict:
    """Timeline alineado por cluster_id (todas las condiciones, fuentes
    resueltas). Reutilizado por /figuras/{slug} y por el resumen en números."""
    figs = {f["slug"]: f for f in manifiesto.cargar()}
    if slug not in figs:
        raise HTTPException(404, f"figura '{slug}' no está en el manifiesto")

    fmap = _fuentes_map(slug)
    conds = [c for c in CONDS_ORDEN if (manifiesto.salidas_dir(slug) / f"{c}.json").exists()]

    indice: dict[str, dict] = {}
    for cond in conds:
        for e in _cargar_cond(slug, cond):
            cid = e.get("cluster_id") or f"{e['fecha']}|{','.join(sorted(e.get('fuentes', [])))}"
            d = indice.setdefault(
                cid, {"cluster_id": cid, "fecha": e["fecha"], "fuentes": set(), "por_condicion": {}}
            )
            d["fuentes"].update(e.get("fuentes", []))
            d["por_condicion"][cond] = e["resumen"]

    eventos = []
    for d in sorted(indice.values(), key=lambda d: d["fecha"]):
        fuentes = [
            {"doc_id": f, **fmap.get(f, {"url": "", "titulo": "", "lead": ""})}
            for f in sorted(d["fuentes"])
        ]
        eventos.append({
            "cluster_id": d["cluster_id"],
            "fecha": d["fecha"],
            "fuentes": fuentes,
            "por_condicion": d["por_condicion"],
        })

    return {"slug": slug, "nombre": figs[slug]["nombre"], "condiciones": conds, "eventos": eventos}


@app.get("/api/figuras/{slug}")
def figura(slug: str) -> dict:
    return _eventos_figura(slug)


def _gold_procesal(slug: str) -> dict | None:
    """Gold procesal humano (tipo/estatus por cluster_id) si existe — hook que
    convierte el Bloque 2 de 'categorización del sistema' a 'verificado'."""
    ruta = GOLD_PROCESAL / f"{slug}_procesal.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


@app.get("/api/figuras/{slug}/resumen")
def resumen(slug: str) -> dict:
    """Resumen en números (read-only, sin LLM): bloque 1 (conteos exactos) +
    bloque 2 (categorización procesal por reglas, auditable, o gold si existe)."""
    payload = _eventos_figura(slug)
    return resumen_mod.computar(
        payload, n_notas_corpus=len(_fuentes_map(slug)), gold=_gold_procesal(slug)
    )


class CrearFigura(BaseModel):
    nombre: str
    homonimos: list[str] = []
    terminos: list[str] = []


@app.post("/api/figuras")
def crear_figura(body: CrearFigura) -> dict:
    """Lanza el precómputo de una figura nueva como JOB en background (nunca en
    el request). Devuelve el slug y el estado para que la web haga polling."""
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(400, "El nombre no puede estar vacío.")
    slug = jobs.slugify(nombre)
    if not slug:
        raise HTTPException(400, "Nombre inválido.")
    if slug in {f["slug"] for f in manifiesto.cargar()}:
        return {"slug": slug, "estado": "done", "nota": "ya existe"}
    est = jobs.leer_estado(slug)
    if est and est.get("estado") == "running":
        return {"slug": slug, "estado": "running"}
    jobs.lanzar(slug, nombre, body.homonimos, body.terminos)
    return {"slug": slug, "estado": "running"}


@app.get("/api/jobs/{slug}")
def estado_job(slug: str) -> dict:
    """Estado del job de precómputo (running/done/error) + cola del log."""
    return jobs.estado(slug)


# El frontend estático se monta al final para no tapar las rutas /api/*.
if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
