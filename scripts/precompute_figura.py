"""Precómputo OFFLINE de una figura → salidas servibles por la web app.

Corre el pipeline genérico para la figura `<slug>` (config en src/figuras.py) y
deja todo listo para que la app lo sirva, SIN ejecutar nada en vivo desde el
request:
  - corpus:  data/corpus_<slug>.parquet
  - salidas: data/salidas/<slug>/{b0_lead,b1_extractive,sistema_rag,ablacion}.json
  - grafo:   data/graph_<slug>.duckdb
  - registra la figura en data/figuras.json (manifiesto)

La config por figura (gazetteer de desambiguación + homónimos a excluir +
queries + ventana) es lo que evita que el timeline salga contaminado.

Requiere ANTHROPIC_API_KEY (en .env) para Sistema/Ablación; sin ella genera solo
B0/B1. Andina como fuente primaria. Este script toma varios minutos (scraping +
LLM): córrelo OFFLINE, nunca dentro de un request web.

Uso:  python scripts/precompute_figura.py <slug>        (p. ej. humala)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict

import pandas as pd

from src import figuras, manifiesto
from src.generation import _llm
from src.generation.ablacion import Ablacion
from src.generation.b0_lead import B0Lead
from src.generation.b1_extractive import B1Extractive
from src.generation.base import GenerationCondition
from src.generation.sistema_rag import SistemaRAG
from src.ingest import andina
from src.ingest._util import dentro_de_ventana, http_session
from src.pipeline import cluster, entities, preprocess, salience
from src.pipeline.entity_discovery import descubrir_entidades
from src.pipeline.protagonism import clasificar
from src.pipeline.relation_classifier import HybridClassifier
from src.pipeline.relations import extraer_coocurrencias
from src.schemas import Documento, RelationEdge
from src.storage import KnowledgeGraph

log = logging.getLogger(__name__)

MODELO_NER = "es_core_news_md"
DELAY = 0.4  # cortesía entre descargas


def _descubrir(session, cfg) -> dict[str, set[str]]:
    proc: dict[str, set[str]] = {}
    for q in cfg.queries:
        urls = andina.buscar(session, q)
        log.info("  query %r: %d URLs", q, len(urls))
        for u in urls:
            proc.setdefault(u, set()).add(q)
    return proc


def precompute(slug: str) -> None:
    cfg = figuras.cargar(slug)
    log.info(
        "== PRECÓMPUTO '%s' (%s) · ventana %s…%s ==",
        cfg.slug,
        cfg.nombre,
        cfg.desde,
        cfg.hasta,
    )

    corpus = manifiesto.corpus_path(slug)

    if corpus.exists():
        log.info("[1-2] corpus ya existe — cargando desde %s (omite scraping)", corpus)
        df = pd.read_parquet(corpus)
        docs = []
        for r in df.to_dict(orient="records"):
            docs.append(
                Documento(
                    doc_id=r["doc_id"],
                    fuente=r["fuente"],
                    url=r["url"],
                    fecha_pub=pd.Timestamp(r["fecha_pub"]).date(),  # ty: ignore[invalid-argument-type]
                    texto=r["texto"],
                    entidades=[],
                )
            )
        log.info("    %d docs cargados", len(docs))
    else:
        session = http_session()
        log.info("[1] descubrimiento (Andina)")
        proc = _descubrir(session, cfg)
        log.info("    URLs únicas: %d", len(proc))

        log.info("[2] descarga + parseo + ventana")
        docs = []
        for k, url in enumerate(proc, 1):
            d = andina.parse_nota(session, url)
            if d and dentro_de_ventana(d.fecha_pub, desde=cfg.desde, hasta=cfg.hasta):
                docs.append(d)
            if k % 100 == 0:
                log.info("    %d/%d (ok=%d)", k, len(proc), len(docs))
            time.sleep(DELAY)
        docs = preprocess.preprocess(docs)
        log.info("    en ventana tras preprocess: %d", len(docs))

        corpus.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "doc_id": d.doc_id,
                    "fuente": d.fuente,
                    "url": d.url,
                    "fecha_pub": d.fecha_pub.isoformat(),
                    "texto": d.texto,
                }
                for d in docs
            ]
        ).to_parquet(corpus, index=False)
        log.info("    corpus → %s (%d docs)", corpus, len(docs))

    log.info("[3] NER + linking (gazetteer de %s)", cfg.slug)
    docs = entities.link_entities(docs, gazetteer=cfg.gazetteer, modelo=MODELO_NER)

    log.info("[4] filtro de protagonismo")
    protag = [
        d
        for d in docs
        if clasificar(d, sujeto_id=cfg.sujeto_id, familia_otros=cfg.familia_otros)
        == "protagonista"
    ]
    log.info("    protagonista: %d de %d", len(protag), len(docs))

    log.info("[5] clustering + saliencia")
    formas_sujeto = [
        sup for sup, (cid, _nombre) in cfg.gazetteer.items() if cid == cfg.sujeto_id
    ]
    salientes = salience.select_salient(
        cluster.cluster_events(protag),
        sujeto_patron=salience.patron_sujeto(formas_sujeto),
    )
    log.info("    eventos salientes: %d", len(salientes))

    log.info("[6] grafo de relaciones")
    grafo_prev = manifiesto.grafo_path(slug)
    if grafo_prev.exists():
        grafo_prev.unlink()
        log.info("    grafo anterior eliminado (re-run limpio)")
    entidades = descubrir_entidades(protag, top_n=40)
    log.info("    entidades descubiertas: %d", len(entidades))

    clasificador = HybridClassifier()

    # Recopilamos todas las co-ocurrencias y agrupamos por par de entidades.
    # Así el LLM se llama UNA VEZ por par (no por oración), reduciendo las
    # llamadas de O(co-ocurrencias) a O(pares únicos) — típicamente 50-100
    # en vez de varios cientos.
    todas_coocs = list(extraer_coocurrencias(protag, entidades))
    log.info("    co-ocurrencias totales: %d", len(todas_coocs))

    por_par: dict[tuple[str, str], list] = defaultdict(list)
    for cooc in todas_coocs:
        por_par[(cooc.entity_a.entity_id, cooc.entity_b.entity_id)].append(cooc)
    log.info("    pares únicos a clasificar: %d", len(por_par))

    n_rel = 0
    with KnowledgeGraph(slug) as grafo:
        for ent in entidades:
            grafo.upsert_entity(ent)

        for (a_id, b_id), coocs in por_par.items():
            resultado = clasificador.classify_grupo(coocs)
            if resultado.tipo == "mencion" and resultado.confianza < 0.5:
                continue

            # Consolidar evidencias (hasta 5 oraciones únicas) y todas las fuentes.
            evidencias = list(dict.fromkeys(c.oracion for c in coocs))[:5]
            fuentes = list(dict.fromkeys(c.doc_id for c in coocs))
            fecha = min(c.fecha for c in coocs)

            grafo.insert_relation(
                RelationEdge(
                    origen_id=a_id,
                    destino_id=b_id,
                    tipo=resultado.tipo,
                    fecha=fecha,
                    evidencia=evidencias,
                    fuentes=fuentes,
                    confianza=resultado.confianza,
                    metodo=resultado.metodo,
                )
            )
            n_rel += 1

        log.info(
            "    co-ocurrencias: %d → pares: %d → relaciones: %d",
            len(todas_coocs),
            len(por_par),
            n_rel,
        )
        for r in grafo.resumen_por_tipo():
            log.info(
                "      %s: %d (confianza media %.2f)",
                r["tipo"],
                r["n"],
                r["confianza_media"],
            )

    log.info("[7] generación")
    conds: list[GenerationCondition] = [B0Lead(), B1Extractive()]
    if _llm.disponible():
        conds += [SistemaRAG(), Ablacion(sujeto=cfg.nombre)]
    else:
        log.warning(
            "LLM no disponible (revisa RELATIONS_LLM_PROVIDER y su API key) — solo B0/B1"
        )
    destino = manifiesto.salidas_dir(slug)
    destino.mkdir(parents=True, exist_ok=True)
    for cond in conds:
        entries = cond.generate(salientes)
        (destino / f"{cond.name}.json").write_text(
            json.dumps(
                [{**e.model_dump(), "fecha": e.fecha.isoformat()} for e in entries],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info("    %s: %d entradas", cond.name, len(entries))
    if _llm.disponible():
        log.info("    costo LLM: %s", _llm.costo())

    entrada = manifiesto.actualizar(slug, cfg.nombre)
    log.info("[8] manifiesto: %s", entrada)
    log.info("== LISTO ==")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    if len(sys.argv) < 2:
        log.error(
            "Uso: python scripts/precompute_figura.py <slug>\nFiguras configuradas: %s",
            sorted(figuras.FIGURAS),
        )
        raise SystemExit(1)
    precompute(sys.argv[1])
