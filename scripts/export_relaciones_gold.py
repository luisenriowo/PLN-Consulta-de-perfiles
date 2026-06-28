"""Exporta co-ocurrencias de un grafo a CSV para ETIQUETADO HUMANO (Fase 1.1).

Genera el gold de relaciones que consume `eval/relations.py`. Reúsa las entidades
YA descubiertas (leídas del grafo DuckDB) y re-extrae co-ocurrencias del corpus,
así que NO vuelve a correr NER (solo el dep-parser). Pre-rellena `tipo_sugerido`
con la predicción por REGLAS para acelerar el etiquetado; el humano completa la
columna `tipo_gold` (clave de TIPOS_RELACION).

El muestreo es ESTRATIFICADO por tipo sugerido para cubrir los 7 tipos (no solo
los mayoritarios) — clave para que la métrica por tipo tenga soporte.

Requiere haber corrido antes:  python scripts/precompute_tema.py <slug>

Uso:   python scripts/export_relaciones_gold.py <slug> [--n 140]
Salida: annotation/gold_relaciones/<slug>.csv
"""

from __future__ import annotations

import csv
import json
import logging
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src import manifiesto
from src.pipeline.relation_classifier import RuleBasedClassifier
from src.pipeline.relations import extraer_coocurrencias
from src.schemas import Documento, EntityNode
from src.storage import KnowledgeGraph

log = logging.getLogger(__name__)

CAMPOS = [
    "entity_a",
    "entity_b",
    "oracion",
    "doc_id",
    "fecha",
    "triple_sujeto",
    "triple_verbo",
    "triple_objeto",
    "tipo_sugerido",
    "tipo_gold",
]
SALIDA_DIR = Path("annotation/gold_relaciones")


def _entidades_del_grafo(slug: str) -> list[EntityNode]:
    """Reconstruye los EntityNode desde el grafo (incluye alias para `_menciona`)."""
    with KnowledgeGraph(slug, read_only=True) as g:
        filas = g.entities()
    nodos: list[EntityNode] = []
    for e in filas:
        alias = e.get("alias")
        if isinstance(alias, str):
            try:
                alias = json.loads(alias)
            except (json.JSONDecodeError, TypeError):
                alias = []
        nodos.append(
            EntityNode(
                entity_id=e["entity_id"],
                nombre=e["nombre"],
                tipo=e["tipo"],
                alias=list(alias or []),
                n_docs=int(e.get("n_docs", 0) or 0),
                n_menciones=int(e.get("n_menciones", 0) or 0),
            )
        )
    return nodos


def _docs(slug: str) -> list[Documento]:
    df = pd.read_parquet(manifiesto.corpus_path(slug))
    return [
        Documento(
            doc_id=r.doc_id,
            fuente=r.fuente,
            url=r.url,
            fecha_pub=pd.Timestamp(r.fecha_pub).date(),
            texto=r.texto,
        )
        for r in df.itertuples()
    ]


def exportar(slug: str, *, n: int = 140, semilla: int = 42) -> tuple[Path, int]:
    corpus = manifiesto.corpus_path(slug)
    if not corpus.exists():
        raise FileNotFoundError(
            f"No existe {corpus}. Corre antes: python scripts/precompute_tema.py {slug}"
        )
    if not manifiesto.grafo_path(slug).exists():
        raise FileNotFoundError(
            f"No existe el grafo de '{slug}'. Corre: python scripts/precompute_tema.py {slug}"
        )

    docs = _docs(slug)
    entidades = _entidades_del_grafo(slug)
    log.info("docs=%d  entidades=%d", len(docs), len(entidades))

    reglas = RuleBasedClassifier()
    por_tipo: dict[str, list] = defaultdict(list)
    total = 0
    for cooc in extraer_coocurrencias(docs, entidades):
        por_tipo[reglas.classify(cooc).tipo].append(cooc)
        total += 1
    log.info(
        "co-ocurrencias=%d  tipos sugeridos=%s",
        total,
        {t: len(v) for t, v in por_tipo.items()},
    )

    # Muestreo estratificado: reparte n entre los tipos presentes.
    rng = random.Random(semilla)
    tipos = list(por_tipo)
    por_cada = max(1, n // max(1, len(tipos)))
    seleccion: list[tuple[str, object]] = []
    for t in tipos:
        grupo = list(por_tipo[t])
        rng.shuffle(grupo)
        seleccion.extend((t, c) for c in grupo[:por_cada])
    rng.shuffle(seleccion)

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    salida = SALIDA_DIR / f"{slug}.csv"
    with open(salida, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for tipo_sug, c in seleccion:
            tr = c.triple or ("", "", "")
            w.writerow(
                {
                    "entity_a": c.entity_a.nombre,
                    "entity_b": c.entity_b.nombre,
                    "oracion": c.oracion,
                    "doc_id": c.doc_id,
                    "fecha": c.fecha.isoformat(),
                    "triple_sujeto": tr[0],
                    "triple_verbo": tr[1],
                    "triple_objeto": tr[2],
                    "tipo_sugerido": tipo_sug,
                    "tipo_gold": "",
                }
            )
    return salida, len(seleccion)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    os.environ.setdefault("SPACY_DEP_MODEL", "es_core_news_md")
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = 140
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    if not args:
        print("Uso: python scripts/export_relaciones_gold.py <slug> [--n 140]")
        raise SystemExit(1)

    ruta, k = exportar(args[0], n=n)
    print(f"\nExportadas {k} filas -> {ruta}")
    print(
        "Completa la columna 'tipo_gold' (alianza|conflicto|pertenencia|"
        "nombramiento|acusacion|ruptura|mencion) y evalúa con:"
    )
    print(f"  python -m eval.relations {ruta}")
