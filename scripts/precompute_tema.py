"""Precómputo OFFLINE de un TEMA → grafo de conocimiento servible por la web.

Enfoque TEMA-CÉNTRICO (a diferencia de `precompute_figura.py`):
  - NO hay sujeto único ni filtro de protagonismo: el grafo se construye sobre
    TODO el corpus del tema.
  - NO hay gazetteer de desambiguación: las entidades se DESCUBREN del corpus
    (`entity_discovery`) y se enlazan a Wikidata para IDs canónicos.
  - NO genera las 4 condiciones de timeline: el producto es el GRAFO de
    relaciones. La línea de tiempo es una vista derivada (clic en un nodo).

Deja:
  - corpus: data/corpus_<slug>.parquet  (con columna `fuente`, multi-fuente ready)
  - grafo:  data/graph_<slug>.duckdb    (entidades + relaciones)
  - registra el tema en data/figuras.json (manifiesto, tipo="tema")

La clasificación de relaciones usa el LLM solo cuando las reglas no alcanzan
(HybridClassifier). Si no hay API key configurada, degrada a SOLO REGLAS sin
fallar. El lookup de Wikidata se puede desactivar con WIKIDATA_ENRIQUECER=0.

Uso:  python scripts/precompute_tema.py <slug>
      (slug de TEMAS en src/figuras.py, o el slug de una figura/corpus existente
       para reusar su corpus en modo tema-céntrico, p. ej. `humala`)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from src import figuras, manifiesto
from src.generation import _llm
from src.ingest import andina, gdelt
from src.ingest._util import dentro_de_ventana, http_session
from src.pipeline import preprocess
from src.pipeline.entity_discovery import descubrir_entidades
from src.pipeline.relation_classifier import HybridClassifier
from src.pipeline.relations import extraer_coocurrencias
from src.schemas import Documento, RelationEdge
from src.storage import KnowledgeGraph

log = logging.getLogger(__name__)

DELAY = 0.4   # cortesía entre descargas


def _colectar_andina(cfg) -> list[Documento]:
    """Descarga + parsea notas de Andina para las queries del tema (en ventana)."""
    session = http_session()
    proc: dict[str, set[str]] = {}
    for q in cfg.queries:
        urls = andina.buscar(session, q)
        log.info("    andina query %r: %d URLs", q, len(urls))
        for u in urls:
            proc.setdefault(u, set()).add(q)
    log.info("    andina URLs únicas: %d", len(proc))

    docs: list[Documento] = []
    for k, url in enumerate(proc, 1):
        d = andina.parse_nota(session, url)
        if d and dentro_de_ventana(d.fecha_pub, desde=cfg.desde, hasta=cfg.hasta):
            docs.append(d)
        if k % 100 == 0:
            log.info("    andina %d/%d (ok=%d)", k, len(proc), len(docs))
        time.sleep(DELAY)
    return docs


def _colectar_gdelt(cfg) -> list[Documento]:
    """Recolecta titulares de GDELT (medios independientes) por query.

    Una request por query, respetando el rate limit de la DOC API (≥5 s).
    """
    docs: list[Documento] = []
    for i, q in enumerate(cfg.queries):
        if i:
            time.sleep(5.5)   # rate limit GDELT: 1 request / ≥5 s
        try:
            res = gdelt.collect(q, hasta=cfg.hasta, desde=cfg.desde)
        except Exception as exc:   # GDELT no es crítica; no debe tumbar el run
            log.warning("    gdelt query %r falló: %s", q, exc)
            continue
        log.info("    gdelt query %r: %d docs", q, len(res))
        docs.extend(res)
    return docs


_COLECTORES = {"andina": _colectar_andina, "gdelt": _colectar_gdelt}


def _colectar(cfg) -> list[Documento]:
    """Ingesta MULTI-FUENTE: agrega los colectores configurados en cfg.fuentes."""
    docs: list[Documento] = []
    for fuente in cfg.fuentes:
        colector = _COLECTORES.get(fuente)
        if colector is None:
            log.warning("    fuente desconocida %r — se omite", fuente)
            continue
        log.info("[1] colectando fuente: %s", fuente)
        docs.extend(colector(cfg))
    return docs


def _cargar_corpus(slug: str, cfg) -> list[Documento]:
    """Carga el corpus del tema: reusa el parquet si existe, si no lo scrapea.

    Preserva la columna `fuente` (contrato multi-fuente): cada documento sabe de
    qué medio proviene; el dedup de `preprocess` ya es cross-fuente (por firma de
    texto), así que una nota republicada por dos medios cuenta una sola vez.
    """
    corpus = manifiesto.corpus_path(slug)
    if corpus.exists():
        log.info("[1-2] corpus ya existe — cargando desde %s (omite scraping)", corpus)
        df = pd.read_parquet(corpus)
        docs = [
            Documento(
                doc_id=r.doc_id, fuente=r.fuente, url=r.url,
                fecha_pub=pd.Timestamp(r.fecha_pub).date(), texto=r.texto,
                entidades=[],
            )
            for r in df.itertuples()
        ]
        log.info("    %d docs cargados", len(docs))
        return docs

    log.info("[1] ingesta multi-fuente: %s", list(cfg.fuentes))
    docs = _colectar(cfg)

    log.info("[2] preprocess (dedup cross-fuente por firma de texto)")
    crudos = len(docs)
    docs = preprocess.preprocess(docs)
    log.info("    colectados: %d → tras dedup: %d", crudos, len(docs))
    log.info("    distribución por fuente: %s", dict(Counter(d.fuente for d in docs)))

    corpus.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"doc_id": d.doc_id, "fuente": d.fuente, "url": d.url,
         "fecha_pub": d.fecha_pub.isoformat(), "texto": d.texto}
        for d in docs
    ]).to_parquet(corpus, index=False)
    log.info("    corpus → %s (%d docs)", corpus, len(docs))
    return docs


def precompute_tema(slug: str) -> None:
    cfg = figuras.cargar_tema(slug)
    log.info("== PRECÓMPUTO TEMA '%s' (%s) · ventana %s…%s · top_n=%d ==",
             cfg.slug, cfg.nombre, cfg.desde, cfg.hasta, cfg.top_n)

    docs = _cargar_corpus(slug, cfg)
    if not docs:
        log.error("Corpus vacío — nada que procesar para '%s'", slug)
        raise SystemExit(1)

    log.info("[3] descubrimiento de entidades (sobre TODO el corpus, sin protagonismo)")
    enriquecer = os.environ.get("WIKIDATA_ENRIQUECER", "1") != "0"
    entidades = descubrir_entidades(
        docs, top_n=cfg.top_n, pais=cfg.pais, enriquecer_wikidata=enriquecer
    )
    log.info("    entidades descubiertas: %d (top_n=%d, wikidata=%s)",
             len(entidades), cfg.top_n, enriquecer)
    for e in entidades[:10]:
        log.info("      %-28s %-4s n_docs=%d wikidata=%s",
                 e.nombre, e.tipo, e.n_docs, e.wikidata_id or "-")

    log.info("[4] co-ocurrencias")
    todas_coocs = list(extraer_coocurrencias(docs, entidades))
    log.info("    co-ocurrencias totales: %d", len(todas_coocs))

    por_par: dict[tuple[str, str], list] = defaultdict(list)
    for cooc in todas_coocs:
        por_par[(cooc.entity_a.entity_id, cooc.entity_b.entity_id)].append(cooc)
    log.info("    pares únicos a clasificar: %d", len(por_par))

    log.info("[5] clasificación de relaciones + grafo")
    grafo_prev = manifiesto.grafo_path(slug)
    if grafo_prev.exists():
        grafo_prev.unlink()
        log.info("    grafo anterior eliminado (re-run limpio)")

    if _llm.disponible():
        clasificador = HybridClassifier()
    else:
        log.warning("LLM no disponible (revisa RELATIONS_LLM_PROVIDER y su API key) "
                    "— clasificación SOLO por reglas")
        clasificador = HybridClassifier(umbral=0.0)   # nunca escala al LLM

    n_rel = 0
    fechas_rel: list = []
    with KnowledgeGraph(slug) as grafo:
        for ent in entidades:
            grafo.upsert_entity(ent)

        for (a_id, b_id), coocs in por_par.items():
            resultado = clasificador.classify_grupo(coocs)
            if resultado.tipo == "mencion" and resultado.confianza < 0.5:
                continue

            evidencias = list(dict.fromkeys(c.oracion for c in coocs))[:5]
            fuentes    = list(dict.fromkeys(c.doc_id  for c in coocs))
            fecha      = min(c.fecha for c in coocs)
            fechas_rel.append(fecha)

            grafo.insert_relation(RelationEdge(
                origen_id  = a_id,
                destino_id = b_id,
                tipo       = resultado.tipo,
                fecha      = fecha,
                evidencia  = evidencias,
                fuentes    = fuentes,
                confianza  = resultado.confianza,
                metodo     = resultado.metodo,
            ))
            n_rel += 1

        log.info("    co-ocurrencias: %d → pares: %d → relaciones: %d",
                 len(todas_coocs), len(por_par), n_rel)
        for r in grafo.resumen_por_tipo():
            log.info("      %s: %d (confianza media %.2f)",
                     r["tipo"], r["n"], r["confianza_media"])

    if _llm.disponible():
        log.info("    costo LLM: %s", _llm.costo())

    rango = (
        [min(fechas_rel).isoformat(), max(fechas_rel).isoformat()]
        if fechas_rel else None
    )
    entrada = manifiesto.actualizar_tema(
        slug, cfg.nombre,
        n_entidades=len(entidades), n_relaciones=n_rel, rango_fechas=rango,
    )
    log.info("[6] manifiesto: %s", entrada)
    log.info("== LISTO ==")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    # Defaults offline: usar el modelo spaCy de dev (es_core_news_md) si el
    # entorno no fuerza otro. `setdefault` respeta lo que ya venga del .env.
    os.environ.setdefault("SPACY_NER_MODEL", "es_core_news_md")
    os.environ.setdefault("SPACY_DEP_MODEL", "es_core_news_md")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    if len(sys.argv) < 2:
        log.error(
            "Uso: python scripts/precompute_tema.py <slug>\n"
            "Temas configurados: %s\n"
            "(o el slug de una figura/corpus existente para reusar su corpus)",
            sorted(figuras.TEMAS),
        )
        raise SystemExit(1)
    precompute_tema(sys.argv[1])
