"""Producto — Backend FastAPI multi-figura (OBLIGATORIO, CLAUDE.md §9).

READ-ONLY sobre outputs ya precomputados. Lee `data/figuras.json` (manifiesto)
y, por figura, las salidas `data/salidas/<slug>/<cond>.json` + el corpus
`data/corpus_<slug>.parquet`. Alinea las 4 condiciones por `cluster_id`
server-side y resuelve cada fuente a {url, título, lead}. NO ejecuta el pipeline
ni llama al LLM en el request (eso es offline; ver scripts/precompute_figura.py).

Sirve además el frontend estático en `src/app/web/`.

Levantar:  uv run uvicorn src.app.api:app --reload    →    http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import manifiesto
from src.app import jobs
from src.app import resumen as resumen_mod
from src.storage import KnowledgeGraph

log = logging.getLogger(__name__)

WEB = Path(__file__).parent / "web"
GOLD_PROCESAL = Path("annotation/gold")
_DATA = Path(os.environ.get("TIMELINE_DATA_DIR", "data"))

# Orden de presentación de condiciones: Sistema primero (la salida "buena").
CONDS_ORDEN = ["sistema_rag", "b1_extractive", "b0_lead", "ablacion"]

app = FastAPI(title="timeline-gen", description="Líneas de tiempo de figuras políticas")


# ── Helpers internos ───────────────────────────────────────────────────────────


@lru_cache(maxsize=16)
def _fuentes_map_cached(slug: str, _mtime: float) -> dict[str, dict]:
    """doc_id -> {url, titulo, lead}. `_mtime` está en la clave de caché para que
    se invalide sola al reescribir el parquet (p. ej. tras re-precomputar)."""
    corpus = manifiesto.corpus_path(slug)
    if not corpus.exists():
        return {}
    df = pd.read_parquet(corpus, columns=["doc_id", "url", "texto"])
    mapa: dict[str, dict] = {}
    for r in df.to_dict(orient="records"):
        lineas = str(r["texto"]).split("\n")
        mapa[r["doc_id"]] = {
            "url": r["url"],
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
    if not ruta.exists():
        return []
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("No se pudo leer %s: %s", ruta, exc)
        return []


def _check_slug(slug: str) -> None:
    figs = {f["slug"] for f in manifiesto.cargar()}
    if slug not in figs:
        raise HTTPException(404, f"figura '{slug}' no está en el manifiesto")


def _check_grafo(slug: str) -> Path:
    """Valida que el grafo DuckDB de la figura exista."""
    ruta = _DATA / f"graph_{slug}.duckdb"
    if not ruta.exists():
        raise HTTPException(
            404,
            f"Grafo de '{slug}' no existe — corre primero: "
            f"uv run python scripts/precompute_figura.py {slug}",
        )
    return ruta


def _abrir_grafo(slug: str):
    """Context manager wrapper con error HTTP útil si el DuckDB está corrupto.

    Las HTTPException levantadas DENTRO del `with` (404 entidad inexistente,
    400 fecha inválida, etc.) se relanzan tal cual: el 503 sólo cubre fallos
    reales al abrir/leer la BD."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        try:
            with KnowledgeGraph(slug, read_only=True) as g:
                yield g
        except HTTPException:
            raise
        except Exception as exc:
            log.error("Error abriendo grafo de '%s': %s", slug, exc)
            raise HTTPException(
                503, f"Grafo de '{slug}' no disponible temporalmente"
            ) from exc

    return _cm()


# ── Timeline ───────────────────────────────────────────────────────────────────


def _eventos_figura(slug: str) -> dict:
    """Timeline alineado por cluster_id (todas las condiciones, fuentes
    resueltas). Reutilizado por /figuras/{slug} y por el resumen en números."""
    figs = {f["slug"]: f for f in manifiesto.cargar()}
    if slug not in figs:
        raise HTTPException(404, f"figura '{slug}' no está en el manifiesto")

    fmap = _fuentes_map(slug)
    conds = [
        c for c in CONDS_ORDEN if (manifiesto.salidas_dir(slug) / f"{c}.json").exists()
    ]

    indice: dict[str, dict] = {}
    for cond in conds:
        for e in _cargar_cond(slug, cond):
            cid = (
                e.get("cluster_id")
                or f"{e['fecha']}|{','.join(sorted(e.get('fuentes', [])))}"
            )
            d = indice.setdefault(
                cid,
                {
                    "cluster_id": cid,
                    "fecha": e["fecha"],
                    "fuentes": set(),
                    "por_condicion": {},
                },
            )
            d["fuentes"].update(e.get("fuentes", []))
            d["por_condicion"][cond] = e["resumen"]

    eventos = []
    for d in sorted(indice.values(), key=lambda d: d["fecha"]):
        fuentes = [
            {"doc_id": f, **fmap.get(f, {"url": "", "titulo": "", "lead": ""})}
            for f in sorted(d["fuentes"])
        ]
        eventos.append(
            {
                "cluster_id": d["cluster_id"],
                "fecha": d["fecha"],
                "fuentes": fuentes,
                "por_condicion": d["por_condicion"],
            }
        )

    return {
        "slug": slug,
        "nombre": figs[slug]["nombre"],
        "condiciones": conds,
        "eventos": eventos,
    }


# ── Rutas: timeline ────────────────────────────────────────────────────────────


@app.get("/api/figuras")
def figuras() -> list[dict]:
    """Manifiesto: figuras ya procesadas (para el selector)."""
    return manifiesto.cargar()


@app.get("/api/figuras/{slug}")
def figura(slug: str) -> dict:
    return _eventos_figura(slug)


def _gold_procesal(slug: str) -> dict | None:
    """Gold procesal humano (tipo/estatus por cluster_id) si existe — hook que
    convierte el Bloque 2 de 'categorización del sistema' a 'verificado'."""
    ruta = GOLD_PROCESAL / f"{slug}_procesal.json"
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("No se pudo leer gold %s: %s", ruta, exc)
        return None


@app.get("/api/figuras/{slug}/resumen")
def resumen(slug: str) -> dict:
    """Resumen en números (read-only, sin LLM): bloque 1 (conteos exactos) +
    bloque 2 (categorización procesal por reglas, auditable, o gold si existe)."""
    payload = _eventos_figura(slug)
    return resumen_mod.computar(
        payload, n_notas_corpus=len(_fuentes_map(slug)), gold=_gold_procesal(slug)
    )


# ── Rutas: grafo de relaciones ─────────────────────────────────────────────────


@app.get("/api/figuras/{slug}/grafo/entidades")
def grafo_entidades(slug: str) -> list[dict]:
    """Nodos del grafo de relaciones: entidades descubiertas y sus métricas."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        return g.entities()


def _parse_date_or_400(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, f"Fecha inválida: {s!r} — usa formato YYYY-MM-DD")


@app.get("/api/figuras/{slug}/grafo/relaciones")
def grafo_relaciones(
    slug: str,
    desde: Optional[str] = Query(None, description="Fecha inicio ISO (YYYY-MM-DD)"),
    hasta: Optional[str] = Query(None, description="Fecha fin ISO (YYYY-MM-DD)"),
    tipo: Optional[str] = Query(None, description="Tipo de relación"),
    origen_id: Optional[str] = Query(None),
    destino_id: Optional[str] = Query(None),
    min_confianza: float = Query(0.0, ge=0.0, le=1.0),
) -> list[dict]:
    """Aristas del grafo con filtros opcionales. Incluye nombres resueltos de entidades."""
    _check_slug(slug)
    _check_grafo(slug)

    with _abrir_grafo(slug) as g:
        return g.relations(
            desde=_parse_date_or_400(desde),
            hasta=_parse_date_or_400(hasta),
            tipo=tipo,
            origen_id=origen_id,
            destino_id=destino_id,
            min_confianza=min_confianza,
        )


@app.get("/api/figuras/{slug}/grafo/centralidad")
def grafo_centralidad(
    slug: str,
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    min_confianza: float = Query(0.0, ge=0.0, le=1.0),
) -> dict[str, float]:
    """PageRank de cada entidad en el grafo — las más influyentes en el período."""
    _check_slug(slug)
    _check_grafo(slug)

    def _d(s: str | None) -> date | None:
        return date.fromisoformat(s) if s else None

    with _abrir_grafo(slug) as g:
        return g.centralidad(
            desde=_d(desde), hasta=_d(hasta), min_confianza=min_confianza
        )


@app.get("/api/figuras/{slug}/grafo/comunidades")
def grafo_comunidades(
    slug: str,
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    min_confianza: float = Query(0.0, ge=0.0, le=1.0),
) -> list[list[str]]:
    """Comunidades Louvain en el grafo no dirigido — grupos de entidades afines."""
    _check_slug(slug)
    _check_grafo(slug)

    def _d(s: str | None) -> date | None:
        return date.fromisoformat(s) if s else None

    with _abrir_grafo(slug) as g:
        comunidades = g.comunidades(
            desde=_d(desde), hasta=_d(hasta), min_confianza=min_confianza
        )
        return [sorted(c) for c in comunidades]


@app.get("/api/figuras/{slug}/grafo/camino")
def grafo_camino(
    slug: str,
    origen: str = Query(..., description="entity_id origen"),
    destino: str = Query(..., description="entity_id destino"),
) -> list[str]:
    """Camino más corto entre dos entidades. Lista vacía si no hay conexión."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        return g.camino(origen, destino)


@app.get("/api/figuras/{slug}/grafo/relaciones/{rel_id}/evidencia")
def grafo_evidencia(slug: str, rel_id: int) -> dict:
    """Evidencia (oraciones) y fuentes resueltas {doc_id,url,titulo} de una arista."""
    _check_slug(slug)
    _check_grafo(slug)
    fmap = _fuentes_map(slug)
    with _abrir_grafo(slug) as g:
        ev = g.evidencia(rel_id)
    ev["fuentes"] = [
        {"doc_id": d, **fmap.get(d, {"url": "", "titulo": "", "lead": ""})}
        for d in ev["fuentes"]
    ]
    return ev


# ── Rutas: grafo — P4 (búsqueda, evolución, ego, paginación) ─────────────────

@app.get("/api/figuras/{slug}/grafo/stats")
def grafo_stats(slug: str) -> dict:
    """Conteos rápidos del grafo (n_entidades, n_relaciones, rango de fechas)
    para que el frontend decida si cargar el grafo completo o pedir búsqueda."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        return g.stats()


@app.get("/api/figuras/{slug}/grafo/entidades/buscar")
def grafo_entidades_buscar(
    slug: str,
    q: str = Query("", description="Texto a buscar (vacío = top por n_docs)"),
    limit: int = Query(20, ge=1, le=50, description="Máximo de resultados (1-50)"),
) -> list[dict]:
    """Busca entidades por nombre, entity_id o alias. Case-insensitive,
    ordenado por relevancia (exacto > prefijo > contiene > n_docs)."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        return g.search_entities(q, limit=limit)


@app.get("/api/figuras/{slug}/grafo/relaciones/pagina")
def grafo_relaciones_pagina(
    slug: str,
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    origen_id: Optional[str] = Query(None),
    destino_id: Optional[str] = Query(None),
    min_confianza: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=2000, description="Tamaño de página (1-2000)"),
    offset: int = Query(0, ge=0, description="Offset (>=0)"),
    include_total: bool = Query(False, description="Incluir conteo total"),
) -> dict:
    """Relaciones paginadas server-side (filtros iguales a /relaciones). No
    rompe /relaciones (lista simple); este devuelve {items,total,limit,offset}."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        return g.relations_page(
            desde=_parse_date_or_400(desde),
            hasta=_parse_date_or_400(hasta),
            tipo=tipo,
            origen_id=origen_id,
            destino_id=destino_id,
            min_confianza=min_confianza,
            limit=limit,
            offset=offset,
            include_total=include_total,
        )


@app.get("/api/figuras/{slug}/grafo/evolucion")
def grafo_evolucion(
    slug: str,
    entidad_a: str = Query(..., description="entity_id de la primera entidad"),
    entidad_b: str = Query(..., description="entity_id de la segunda entidad"),
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    min_confianza: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(500, ge=1, le=2000, description="Tope de eventos datados"),
) -> dict:
    """Evolución temporal bidireccional entre dos entidades (ambas direcciones,
    ordenadas por fecha). 404 si alguna entidad no existe; 200 con eventos=[]
    si no hay relaciones entre ellas."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        ea = g.entity(entidad_a)
        eb = g.entity(entidad_b)
        if ea is None:
            raise HTTPException(404, f"Entidad no existe: {entidad_a!r}")
        if eb is None:
            raise HTTPException(404, f"Entidad no existe: {entidad_b!r}")

        resultado = g.evolucion_filtrada(
            entidad_a, entidad_b,
            desde=_parse_date_or_400(desde),
            hasta=_parse_date_or_400(hasta),
            tipo=tipo,
            min_confianza=min_confianza,
            limit=limit,
        )
        eventos = resultado["items"]
        # Garantizar contrato: predicado presente (null si esquema viejo)
        for ev in eventos:
            ev.setdefault("predicado", None)
            # Fechas a string para JSON
            f = ev.get("fecha")
            if isinstance(f, date):
                ev["fecha"] = f.isoformat()
        return {
            "entidad_a": {
                "entity_id": ea["entity_id"], "nombre": ea["nombre"],
                "tipo": ea["tipo"],
            },
            "entidad_b": {
                "entity_id": eb["entity_id"], "nombre": eb["nombre"],
                "tipo": eb["tipo"],
            },
            "eventos": eventos,
            "truncado": resultado["truncado"],
            "limit": resultado["limit"],
        }


@app.get("/api/figuras/{slug}/grafo/evolucion/cambios")
def grafo_evolucion_cambios(
    slug: str,
    top_n: int = Query(20, ge=1, le=100, description="Número de pares a devolver (1-100)"),
) -> list[dict]:
    """Pares con más de un tipo de relación a lo largo del tiempo.

    Útil para detectar evoluciones alianza→conflicto y similares.
    Solo opera sobre relaciones tipadas. Devuelve los top_n pares con más
    tipos distintos, cada uno con su secuencia temporal de tipos."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        return g.cambios_relacion(top_n=top_n)


@app.get("/api/figuras/{slug}/grafo/ego/{entity_id}")
def grafo_ego(
    slug: str,
    entity_id: str,
    profundidad: int = Query(1, ge=1, le=2, description="1 o 2"),
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    min_confianza: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    """Ego-grafo on-demand: centro + vecinos (+ vecinos de vecinos si p=2).
    404 si la entidad central no existe. Trunca relaciones por `limit`."""
    _check_slug(slug)
    _check_grafo(slug)
    with _abrir_grafo(slug) as g:
        if g.entity(entity_id) is None:
            raise HTTPException(404, f"Entidad no existe: {entity_id!r}")
        data = g.ego(
            entity_id,
            profundidad=profundidad,
            desde=_parse_date_or_400(desde),
            hasta=_parse_date_or_400(hasta),
            tipo=tipo,
            min_confianza=min_confianza,
            limit=limit,
        )
        # Serializar fechas y normalizar predicado ausente
        for r in data["relaciones"]:
            f = r.get("fecha")
            if isinstance(f, date):
                r["fecha"] = f.isoformat()
            r.setdefault("predicado", None)
        for e in data["entidades"]:
            # alias puede venir como string JSON
            a = e.get("alias")
            if isinstance(a, str):
                try:
                    e["alias"] = json.loads(a) if a else []
                except (json.JSONDecodeError, TypeError):
                    e["alias"] = []
            # metadata no se usa en el frontend; omitir para respuesta liviana
            e.pop("metadata", None)
        return data


# ── Rutas: figuras dinámicas ───────────────────────────────────────────────────


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
    log.info("job lanzado: slug=%s nombre=%r", slug, nombre)
    return {"slug": slug, "estado": "running"}


@app.get("/api/jobs/{slug}")
def estado_job(slug: str) -> dict:
    """Estado del job de precómputo (running/done/error) + cola del log."""
    return jobs.estado(slug)


# El frontend estático se monta al final para no tapar las rutas /api/*.
if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
