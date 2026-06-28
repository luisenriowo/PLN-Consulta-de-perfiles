"""Backbone — Descubrimiento automático de entidades del corpus.

Reemplaza los gazetteers manuales por un proceso de tres etapas que no
requiere ningún input humano por figura:

  1. Extracción  — NER sobre todos los documentos (usa get_ner_model()).
  2. Normalización — limpia cada span de ruido léxico (artículos, temporales),
                     luego agrupa menciones por solapamiento usando ratio de
                     contención (intersec/min) en lugar de Jaccard (intersec/max).
                     El nombre canónico es la forma MÁS FRECUENTE del grupo
                     (no la más larga), con empate roto por la más corta.
  3. Enriquecimiento — Wikidata lookup para IDs canónicos y metadata (cargo,
                        partido, descripción). Cache local en
                        $TIMELINE_DATA_DIR/wikidata_cache.json.
                        Los lookups se hacen en paralelo (WIKIDATA_WORKERS).

El resultado es una lista de EntityNode ordenada por relevancia (frecuencia
de documentos × peso por tipo), lista para alimentar el grafo de relaciones.

Variables de entorno relevantes:
  TIMELINE_DATA_DIR  — directorio raíz de datos (default: "data")
  WIKIDATA_WORKERS   — threads para lookups paralelos (default: 5)
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from src.pipeline._utils import _norm
from src.pipeline.ner import get_ner_model
from src.schemas import Documento, EntityNode

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_DATA_DIR = Path(os.environ.get("TIMELINE_DATA_DIR", "data"))
_CACHE_PATH = _DATA_DIR / "wikidata_cache.json"
_WIKIDATA_WORKERS = int(os.environ.get("WIKIDATA_WORKERS", "5"))

# Peso por tipo de entidad para el ranking (PER > ORG > LOC > MISC).
_PESO_TIPO: dict[str, int] = {"PER": 4, "ORG": 3, "LOC": 2, "MISC": 1}

# Tipos que cuentan como ACTOR político (personas, partidos, instituciones,
# organismos). Erasmo: las entidades de interés son actores, no contexto
# geográfico. El ruido observado en el grafo ("Lima", "Estado", "Cusco", "Ley")
# era LOC/MISC; restringir a PER+ORG lo elimina sin un denylist subjetivo.
_TIPOS_ACTOR: frozenset[str] = frozenset({"PER", "ORG"})

# Términos genéricos que NER a veces etiqueta como PER/ORG pero que no son
# actores específicos (nodos demasiado generales para el grafo). Conservador y
# overridable vía `excluir`. Normalizados (minúsculas, sin acentos).
_GENERICOS: frozenset[str] = frozenset(
    {
        "estado",
        "gobierno",
        "nacion",
        "pais",
        "peru",
        "republica",
        "el estado",
        "el gobierno",
        "el peru",
        "ejecutivo",
    }
)

# Mínimo de tokens válidos (len > 1) para considerar una mención.
_MIN_TOKENS = 1


def _es_actor(info: dict, tipos: frozenset[str], excluir: frozenset[str]) -> bool:
    """True si el grupo de entidad es un actor retenible (tipo permitido y no
    genérico). Aísla el criterio de filtrado para poder testearlo."""
    return info["tipo"] in tipos and _norm(info["nombre"]) not in excluir


# ── Limpieza de spans NER ─────────────────────────────────────────────────

# Temporales y conectores que nunca forman parte de un nombre de entidad.
# spaCy los absorbe por proximidad al span; se eliminan en ambos extremos.
_RUIDO_TEMPORAL: frozenset[str] = frozenset(
    {
        "ayer",
        "hoy",
        "manana",
        "tarde",
        "noche",
        "madrugada",
        "ya",
        "aun",
        "todavia",
        "recien",
        "ahora",
        "luego",
        "tambien",
        "y",
        "o",
        "e",
        "ni",
        "sino",
        "pero",
    }
)

# Palabras que nunca deben iniciar un nombre de entidad.
_RUIDO_INICIO: frozenset[str] = (
    frozenset(
        {
            "el",
            "la",
            "los",
            "las",
            "un",
            "una",
            "unos",
            "unas",
            "al",
            "del",
        }
    )
    | _RUIDO_TEMPORAL
)

# Palabras que nunca deben cerrar un nombre de entidad.
_RUIDO_FIN: frozenset[str] = _RUIDO_TEMPORAL


def _limpiar_span(texto: str) -> str:
    """Elimina palabras de ruido del inicio y fin de un span NER.

    Aplica normalización solo para la comparación; conserva el texto
    original de los tokens que sobreviven para no perder mayúsculas.
    """
    toks = texto.split()
    while toks and _norm(toks[0]) in _RUIDO_INICIO:
        toks = toks[1:]
    while toks and _norm(toks[-1]) in _RUIDO_FIN:
        toks = toks[:-1]
    return " ".join(toks)


def _tokens(texto: str) -> frozenset[str]:
    return frozenset(t for t in _norm(texto).split() if len(t) > 1)


# ── Agrupación de menciones ────────────────────────────────────────────────


def _agrupar(
    menciones: list[tuple[str, str, str]],  # (texto, tipo, doc_id)
) -> dict[str, dict]:
    """Agrupa menciones limpias por solapamiento de tokens.

    Criterio de merge: usa ratio de contención (intersec / min(|A|, |B|))
    en lugar de Jaccard (intersec / max). Esto captura correctamente los
    casos donde un nombre es subconjunto del otro (e.g. "Partido Nacionalista"
    ⊆ "Partido Nacionalista Peruano"). Umbral: 0.7.

    El nombre canónico del grupo es la forma más frecuente en el corpus.
    En caso de empate, se prefiere la más corta (más genérica y estable).

    Retorna {slug: {nombre, tipo, alias, n_menciones, n_docs}}.
    """
    grupos: list[dict] = []

    for texto_raw, tipo, doc_id in menciones:
        texto = _limpiar_span(texto_raw)
        if not texto:
            continue
        toks = _tokens(texto)
        if len(toks) < _MIN_TOKENS:
            continue

        mejor_g = None
        mejor_ov = 0.0
        for g in grupos:
            if g["tipo"] != tipo:
                continue
            intersec = len(toks & g["tokens"])
            if intersec == 0:
                continue
            # Ratio de contención: cuánto del conjunto más pequeño está cubierto.
            ratio = intersec / min(len(toks), len(g["tokens"]))
            if ratio >= 0.7 and intersec > mejor_ov:
                mejor_g = g
                mejor_ov = intersec

        if mejor_g is None:
            grupos.append(
                {
                    "tokens": toks,
                    "tipo": tipo,
                    "frecuencias": {texto: 1},  # {forma: count}
                    "doc_ids": {doc_id},
                    "n_menciones": 1,
                }
            )
        else:
            mejor_g["tokens"] |= toks
            mejor_g["n_menciones"] += 1
            mejor_g["doc_ids"].add(doc_id)
            frecs = mejor_g["frecuencias"]
            frecs[texto] = frecs.get(texto, 0) + 1

    resultado: dict[str, dict] = {}
    for g in grupos:
        # Canónico = más frecuente; empate → más corto (más genérico).
        canonical = max(
            g["frecuencias"].items(),
            key=lambda kv: (kv[1], -len(kv[0])),
        )[0]
        alias = [k for k in g["frecuencias"] if k != canonical]
        slug = re.sub(r"[^a-z0-9]+", "-", _norm(canonical)).strip("-")
        resultado[slug] = {
            "nombre": canonical,
            "tipo": g["tipo"],
            "alias": alias,
            "n_menciones": g["n_menciones"],
            "n_docs": len(g["doc_ids"]),
        }
    return resultado


# ── Wikidata ───────────────────────────────────────────────────────────────


def _cargar_cache() -> dict:
    """Lee el cache local desde disco. Sin memoización — cada llamada es fresca."""
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _guardar_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _fetch_wikidata(nombre: str, tipo: str, pais: str) -> dict | None:
    """HTTP lookup en Wikidata — sin operaciones de cache. Apto para ThreadPoolExecutor.

    Retorna {wikidata_id, metadata} o None si no encuentra coincidencia.
    Errores de red se silencian (Wikidata no es crítico).
    """
    params = {
        "action": "wbsearchentities",
        "search": nombre,
        "language": "es",
        "type": "item",
        "format": "json",
        "limit": 5,
    }
    try:
        resp = requests.get(_WIKIDATA_API, params=params, timeout=8)
        resp.raise_for_status()
        items = resp.json().get("search", [])
    except Exception:
        return None

    pais_norm = _norm(pais)
    for item in items:
        desc = _norm(item.get("description") or "")
        if pais_norm in desc or "politic" in desc or "peruan" in desc:
            return {
                "wikidata_id": item["id"],
                "metadata": {"descripcion": item.get("description", "")},
            }
    return None


# ── API pública ────────────────────────────────────────────────────────────


def descubrir_entidades(
    docs: list[Documento],
    *,
    top_n: int = 20,
    pais: str = "Perú",
    enriquecer_wikidata: bool = True,
    tipos: frozenset[str] | set[str] | None = None,
    excluir: frozenset[str] | set[str] | None = None,
) -> list[EntityNode]:
    """Descubre y rankea las entidades más relevantes del corpus.

    Por defecto retiene solo ACTORES (PER+ORG) y descarta términos genéricos:
    el grafo tema-céntrico modela actores (personas, partidos, instituciones),
    no contexto geográfico. El filtro se aplica ANTES del corte `top_n`, así que
    `top_n=20` devuelve 20 actores, no 20 entidades mixtas reducidas luego.

    Args:
        docs:                Lista de documentos a analizar.
        top_n:               Número máximo de entidades a devolver.
        pais:                Contexto geográfico para el lookup de Wikidata.
        enriquecer_wikidata: Si True, consulta Wikidata en paralelo.
        tipos:               Tipos NER a retener (default `_TIPOS_ACTOR` = PER+ORG;
                             pasa {"PER","ORG","LOC","MISC"} para no filtrar).
        excluir:             Formas canónicas (se normalizan) a descartar como
                             genéricas (default `_GENERICOS`; pasa `set()` para
                             no excluir ninguna).

    Returns:
        Lista de EntityNode ordenada por relevancia (n_docs × peso de tipo).
        Cada nodo incluye el campo `alias` con todas las formas alternativas
        detectadas en el corpus, para que `_menciona` en relations.py
        pueda identificar más co-ocurrencias.
    """
    tipos_keep = frozenset(tipos) if tipos is not None else _TIPOS_ACTOR
    excluir_norm = (
        frozenset(_norm(e) for e in excluir) if excluir is not None else _GENERICOS
    )

    ner = get_ner_model()
    textos = [d.texto for d in docs]

    menciones_raw: list[tuple[str, str, str]] = []
    for doc, menciones in zip(docs, ner(textos)):
        for m in menciones:
            menciones_raw.append((m.texto, m.tipo, doc.doc_id))

    grupos = _agrupar(menciones_raw)
    grupos = {
        slug: info
        for slug, info in grupos.items()
        if _es_actor(info, tipos_keep, excluir_norm)
    }
    ordenados = sorted(
        grupos.items(),
        key=lambda kv: kv[1]["n_docs"] * _PESO_TIPO.get(kv[1]["tipo"], 1),
        reverse=True,
    )[:top_n]

    # ── Wikidata en paralelo ──────────────────────────────────────────────
    cache: dict = {}
    if enriquecer_wikidata:
        cache = _cargar_cache()

        pendientes = [
            (slug, info)
            for slug, info in ordenados
            if f"{_norm(info['nombre'])}::{info['tipo']}" not in cache
        ]

        if pendientes:
            with ThreadPoolExecutor(max_workers=_WIKIDATA_WORKERS) as pool:
                futures = {
                    pool.submit(_fetch_wikidata, info["nombre"], info["tipo"], pais): (
                        slug,
                        info,
                    )
                    for slug, info in pendientes
                }
                for future in as_completed(futures):
                    _, info = futures[future]
                    key = f"{_norm(info['nombre'])}::{info['tipo']}"
                    cache[key] = future.result()

            _guardar_cache(cache)

    # ── Construcción de EntityNode ────────────────────────────────────────
    nodos: list[EntityNode] = []
    for slug, info in ordenados:
        key = f"{_norm(info['nombre'])}::{info['tipo']}"
        wk = cache.get(key) if enriquecer_wikidata else None
        nodos.append(
            EntityNode(
                entity_id=wk["wikidata_id"] if wk else slug,
                nombre=info["nombre"],
                tipo=info["tipo"],
                alias=info["alias"],
                wikidata_id=wk["wikidata_id"] if wk else None,
                n_docs=info["n_docs"],
                n_menciones=info["n_menciones"],
                metadata=wk.get("metadata", {}) if wk else {},
            )
        )
    return nodos
