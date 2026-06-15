"""Precómputo OFFLINE de una figura → salidas servibles por la web app.

Corre el pipeline genérico para la figura `<slug>` (config en src/figuras.py) y
deja todo listo para que la app lo sirva, SIN ejecutar nada en vivo desde el
request:
  - corpus:  data/corpus_<slug>.parquet
  - salidas: data/salidas/<slug>/{b0_lead,b1_extractive,sistema_rag,ablacion}.json
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
import sys
import time
from pathlib import Path

import pandas as pd

from src import figuras, manifiesto
from src.generation import _llm
from src.generation.ablacion import Ablacion
from src.generation.b0_lead import B0Lead
from src.generation.b1_extractive import B1Extractive
from src.generation.sistema_rag import SistemaRAG
from src.ingest import andina
from src.ingest._util import dentro_de_ventana, http_session
from src.pipeline import cluster, entities, preprocess, salience
from src.pipeline.protagonism import clasificar

MODELO_NER = "es_core_news_md"
DELAY = 0.4   # cortesía entre descargas


def _descubrir(session, cfg) -> dict[str, set[str]]:
    proc: dict[str, set[str]] = {}
    for q in cfg.queries:
        urls = andina.buscar(session, q)
        print(f"    query {q!r}: {len(urls)} URLs")
        for u in urls:
            proc.setdefault(u, set()).add(q)
    return proc


def precompute(slug: str) -> None:
    cfg = figuras.cargar(slug)
    print(f"== PRECÓMPUTO '{cfg.slug}' ({cfg.nombre}) · ventana {cfg.desde}…{cfg.hasta} ==")
    session = http_session()

    print("  [1] descubrimiento (Andina)")
    proc = _descubrir(session, cfg)
    print(f"      URLs únicas: {len(proc)}")

    print("  [2] descarga + parseo + ventana")
    docs = []
    for k, url in enumerate(proc, 1):
        d = andina.parse_nota(session, url)
        if d and dentro_de_ventana(d.fecha_pub, desde=cfg.desde, hasta=cfg.hasta):
            docs.append(d)
        if k % 100 == 0:
            print(f"      {k}/{len(proc)} (ok={len(docs)})")
        time.sleep(DELAY)
    docs = preprocess.preprocess(docs)
    print(f"      en ventana tras preprocess: {len(docs)}")

    print(f"  [3] NER + linking (gazetteer de {cfg.slug})")
    docs = entities.link_entities(docs, gazetteer=cfg.gazetteer, modelo=MODELO_NER)

    print("  [4] filtro de protagonismo")
    protag = [
        d for d in docs
        if clasificar(d, sujeto_id=cfg.sujeto_id, familia_otros=cfg.familia_otros)
        == "protagonista"
    ]
    print(f"      protagonista: {len(protag)} de {len(docs)}")

    # corpus servible (para resolver fuentes en la app)
    corpus = manifiesto.corpus_path(slug)
    corpus.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"doc_id": d.doc_id, "fuente": d.fuente, "url": d.url,
         "fecha_pub": d.fecha_pub.isoformat(), "texto": d.texto}
        for d in docs
    ]).to_parquet(corpus, index=False)
    print(f"      corpus → {corpus} ({len(docs)} docs)")

    print("  [5] clustering + saliencia")
    salientes = salience.select_salient(cluster.cluster_events(protag))
    print(f"      eventos salientes: {len(salientes)}")

    print("  [6] generación")
    conds = [B0Lead(), B1Extractive()]
    if _llm.disponible():
        conds += [SistemaRAG(), Ablacion(sujeto=cfg.nombre)]
    else:
        print("      ⚠ sin ANTHROPIC_API_KEY: solo B0/B1")
    destino = manifiesto.salidas_dir(slug)
    destino.mkdir(parents=True, exist_ok=True)
    for cond in conds:
        entries = cond.generate(salientes)
        (destino / f"{cond.name}.json").write_text(
            json.dumps(
                [{**e.model_dump(), "fecha": e.fecha.isoformat()} for e in entries],
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"      {cond.name}: {len(entries)} entradas")
    if _llm.disponible():
        print(f"      costo LLM: {_llm.costo()}")

    entrada = manifiesto.actualizar(slug, cfg.nombre)
    print(f"  [7] manifiesto: {entrada}")
    print("== LISTO ==")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Uso: python scripts/precompute_figura.py <slug>\n"
              f"Figuras configuradas: {sorted(figuras.FIGURAS)}")
        raise SystemExit(1)
    precompute(sys.argv[1])
