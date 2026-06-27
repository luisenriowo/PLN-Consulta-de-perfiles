"""Builder del GRAFO TEMPORAL de relaciones ABIERTAS (OpenIE, sin LLM).

Consume un corpus (parquet `corpus_<slug>.parquet` o el JSONL del crawler) y
produce un grafo donde cada arista es una **relación abierta fechada**: (entidad
A, predicado-verbo, entidad B, fecha, evidencia). NO colapsa por par → el mismo
par puede tener varias aristas en el tiempo, así se ve cómo EVOLUCIONA la
relación. El TIPO no se asigna aquí: se identifica después (WS3).

Etapas: filtro de idioma (descarta inglés) → descubrir entidades (actores) →
`extraer_relaciones_abiertas` → dedup por (par, fecha, predicado) → grafo DuckDB.

Uso:
  python scripts/build_open_graph.py <slug>                 # usa data/corpus_<slug>.parquet
  python scripts/build_open_graph.py andina --jsonl data/andina_crawl.jsonl --top-n 300
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path

import pandas as pd

from src import manifiesto
from src.pipeline.entity_discovery import descubrir_entidades
from src.pipeline.relations import extraer_relaciones_abiertas
from src.schemas import Documento, RelationEdge
from src.storage import KnowledgeGraph

log = logging.getLogger(__name__)

# Filtro de idioma (heurístico, sin dependencias): palabras función ES vs EN.
_ES = {"de", "la", "el", "que", "en", "los", "del", "las", "una", "por",
       "con", "para", "su", "al", "se", "lo", "como", "más"}
_EN = {"the", "of", "and", "to", "in", "for", "on", "with", "as", "by",
       "that", "is", "was", "from", "at", "this"}
_RE_TOK = re.compile(r"[a-záéíóúñ]+")


def es_espanol(texto: str) -> bool:
    """True si el texto parece español (más stopwords ES que EN en el inicio)."""
    toks = _RE_TOK.findall(texto[:400].lower())
    if not toks:
        return True
    es = sum(t in _ES for t in toks)
    en = sum(t in _EN for t in toks)
    return es >= en


def _cargar(slug: str, jsonl: Path | None) -> list[Documento]:
    if jsonl is not None:
        docs = []
        with jsonl.open(encoding="utf-8") as f:
            for linea in f:
                r = json.loads(linea)
                docs.append(Documento(
                    doc_id=r["doc_id"], fuente=r["fuente"], url=r["url"],
                    fecha_pub=pd.Timestamp(r["fecha_pub"]).date(), texto=r["texto"],
                ))
        return docs
    df = pd.read_parquet(manifiesto.corpus_path(slug))
    return [
        Documento(doc_id=r.doc_id, fuente=r.fuente, url=r.url,
                  fecha_pub=pd.Timestamp(r.fecha_pub).date(), texto=r.texto)
        for r in df.itertuples()
    ]


def build(slug: str, *, jsonl: Path | None = None, top_n: int = 300,
          enriquecer_wikidata: bool = False, corpus_slug: str | None = None) -> dict:
    docs = _cargar(corpus_slug or slug, jsonl)
    log.info("docs cargados: %d", len(docs))
    docs = [d for d in docs if es_espanol(d.texto)]
    log.info("tras filtro de idioma (ES): %d", len(docs))

    log.info("descubriendo entidades (top_n=%d)…", top_n)
    entidades = descubrir_entidades(docs, top_n=top_n, enriquecer_wikidata=enriquecer_wikidata)
    log.info("entidades: %d", len(entidades))

    grafo_prev = manifiesto.grafo_path(slug)
    if grafo_prev.exists():
        grafo_prev.unlink()
        log.info("grafo anterior eliminado (re-run limpio)")

    log.info("extrayendo relaciones abiertas fechadas…")
    vistos: set = set()
    n = 0
    with KnowledgeGraph(slug) as g:
        for ent in entidades:
            g.upsert_entity(ent)
        for rel in extraer_relaciones_abiertas(docs, entidades):
            clave = (rel.entity_a.entity_id, rel.entity_b.entity_id,
                     rel.fecha.isoformat(), rel.predicado)
            if clave in vistos:
                continue
            vistos.add(clave)
            g.insert_relation(RelationEdge(
                origen_id=rel.entity_a.entity_id, destino_id=rel.entity_b.entity_id,
                tipo=None, predicado=rel.predicado, fecha=rel.fecha,
                evidencia=[rel.oracion], fuentes=[rel.doc_id],
                confianza=1.0, metodo="openie",
            ))
            n += 1
            if n % 500 == 0:
                log.info("  aristas abiertas: %d", n)

    log.info("== LISTO == entidades=%d aristas_abiertas=%d", len(entidades), n)
    return {"entidades": len(entidades), "aristas": n}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    os.environ.setdefault("SPACY_NER_MODEL", "es_core_news_md")
    os.environ.setdefault("SPACY_DEP_MODEL", "es_core_news_md")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="Grafo temporal de relaciones abiertas")
    p.add_argument("slug")
    p.add_argument("--jsonl", type=Path, default=None, help="corpus JSONL del crawler")
    p.add_argument("--corpus-slug", default=None, help="slug del corpus parquet a leer (si difiere)")
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument("--wikidata", action="store_true", help="enriquecer entidades con Wikidata")
    args = p.parse_args()
    build(args.slug, jsonl=args.jsonl, top_n=args.top_n,
          enriquecer_wikidata=args.wikidata, corpus_slug=args.corpus_slug)
