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
from pathlib import Path

import pandas as pd

from src import manifiesto
from src.pipeline.entity_discovery import descubrir_entidades
from src.pipeline.preprocess import es_espanol
from src.pipeline.relations import extraer_relaciones_abiertas
from src.schemas import Documento, RelationEdge
from src.storage import KnowledgeGraph

log = logging.getLogger(__name__)



def _cargar(slug: str, jsonl: Path | None) -> list[Documento]:
    if jsonl is not None:
        docs = []
        with jsonl.open(encoding="utf-8") as f:
            for linea in f:
                r = json.loads(linea)
                docs.append(
                    Documento(
                        doc_id=r["doc_id"],
                        fuente=r["fuente"],
                        url=r["url"],
                        fecha_pub=pd.Timestamp(r["fecha_pub"]).date(),  # ty: ignore[invalid-argument-type]
                        texto=r["texto"],
                    )
                )
        return docs
    df = pd.read_parquet(manifiesto.corpus_path(slug))
    docs = []
    for r in df.to_dict(orient="records"):
        docs.append(
            Documento(
                doc_id=r["doc_id"],
                fuente=r["fuente"],
                url=r["url"],
                fecha_pub=pd.Timestamp(r["fecha_pub"]).date(),  # ty: ignore[invalid-argument-type]
                texto=r["texto"],
            )
        )
    return docs


def build(
    slug: str,
    *,
    jsonl: Path | None = None,
    top_n: int = 300,
    enriquecer_wikidata: bool = False,
    corpus_slug: str | None = None,
    usar_menciones: bool = False,
) -> dict:
    # Archivo de progreso legible en vivo (sin el bloqueo exclusivo del DuckDB).
    prog_path = Path("data") / f"{slug}_progress.txt"

    def prog(msg: str) -> None:
        try:
            prog_path.write_text(msg + "\n", encoding="utf-8")
        except Exception:
            pass

    prog("cargando corpus…")
    docs = _cargar(corpus_slug or slug, jsonl)
    log.info("docs cargados: %d", len(docs))
    prog(f"docs={len(docs)} · filtrando idioma…")
    docs = [d for d in docs if es_espanol(d.texto)]
    log.info("tras filtro de idioma (ES): %d", len(docs))

    # Reusar menciones NER persistidas (scripts/ner_corpus.py) en vez de re-correr
    # NER. La ruta de menciones se deriva del corpus parquet (solo modo parquet).
    menc = None
    if usar_menciones and jsonl is None:
        from scripts.ner_corpus import cargar_menciones

        prog(f"docs ES={len(docs)} · cargando menciones NER…")
        menc = cargar_menciones(manifiesto.corpus_path(corpus_slug or slug))
        log.info("usando %d menciones NER persistidas (sin re-NER)", len(menc))

    prog(
        f"RESOLVIENDO ENTIDADES sobre {len(menc) if menc else 0} menciones "
        f"(fase lenta, sin progreso fino)…"
    )
    log.info("descubriendo entidades (top_n=%d)…", top_n)
    entidades = descubrir_entidades(
        docs, top_n=top_n, enriquecer_wikidata=enriquecer_wikidata, menciones=menc
    )
    log.info("entidades: %d", len(entidades))

    grafo_prev = manifiesto.grafo_path(slug)
    if grafo_prev.exists():
        grafo_prev.unlink()
        log.info("grafo anterior eliminado (re-run limpio)")

    log.info("extrayendo relaciones abiertas fechadas…")
    vistos: set = set()

    def _aristas():
        # Genera aristas abiertas únicas (dedup por par+fecha+predicado+doc+oración).
        for rel in extraer_relaciones_abiertas(docs, entidades):
            clave = (
                rel.entity_a.entity_id,
                rel.entity_b.entity_id,
                rel.fecha.isoformat(),
                rel.predicado,
                rel.doc_id,
                rel.oracion,
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            yield RelationEdge(
                origen_id=rel.entity_a.entity_id,
                destino_id=rel.entity_b.entity_id,
                tipo=None,
                predicado=rel.predicado,
                fecha=rel.fecha,
                evidencia=[rel.oracion],
                fuentes=[rel.doc_id],
                confianza=1.0,
                metodo="openie",
            )

    prog(f"entidades={len(entidades)} · EXTRAYENDO+INSERTANDO relaciones…")
    with KnowledgeGraph(slug) as g:
        for ent in entidades:
            g.upsert_entity(ent)
        # Inserción en BLOQUE (un commit por lote) — evita el cuello de los inserts
        # de a una arista, que dominaban el tiempo a escala de archivo.
        n = g.insert_relations_bulk(
            _aristas(),
            on_batch=lambda t: prog(
                f"entidades={len(entidades)} · relaciones insertadas: {t:,}"
            ),
        )

    prog(f"LISTO · entidades={len(entidades)} aristas={n}")
    log.info("== LISTO == entidades=%d aristas_abiertas=%d", len(entidades), n)
    return {"entidades": len(entidades), "aristas": n}


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    os.environ.setdefault("SPACY_NER_MODEL", "es_core_news_md")
    os.environ.setdefault("SPACY_DEP_MODEL", "es_core_news_md")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    p = argparse.ArgumentParser(description="Grafo temporal de relaciones abiertas")
    p.add_argument("slug")
    p.add_argument("--jsonl", type=Path, default=None, help="corpus JSONL del crawler")
    p.add_argument(
        "--corpus-slug",
        default=None,
        help="slug del corpus parquet a leer (si difiere)",
    )
    p.add_argument("--top-n", type=int, default=300)
    p.add_argument(
        "--wikidata", action="store_true", help="enriquecer entidades con Wikidata"
    )
    p.add_argument(
        "--menciones", action="store_true",
        help="reusar menciones NER persistidas (scripts/ner_corpus.py) en vez de re-NER",
    )
    args = p.parse_args()
    build(
        args.slug,
        jsonl=args.jsonl,
        top_n=args.top_n,
        enriquecer_wikidata=args.wikidata,
        corpus_slug=args.corpus_slug,
        usar_menciones=args.menciones,
    )
