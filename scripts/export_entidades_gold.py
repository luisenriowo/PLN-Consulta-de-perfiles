"""Exporta entidades descubiertas a CSV para ETIQUETADO HUMANO (Fase 2.1/2.3).

Genera el gold que consume `eval/entities.py`. Descubre el conjunto CRUDO de
entidades (todos los tipos, sin denylist) y marca cuáles SOBREVIVEN el filtro de
actores (`retenida`). Así, en un solo archivo, el humano puede juzgar:
  - precision: de las retenidas, ¿cuántas son actores reales? (ruido que pasa)
  - recall:    de los actores reales, ¿cuántas se retuvieron? (actores perdidos)

El humano completa: es_actor_gold (1/0), tipo_correcto (PER|ORG|LOC|MISC) y
nombre_canonico (para detectar splits del mismo actor).

Requiere el corpus:  data/corpus_<slug>.parquet  (de precompute_tema/figura).

Uso:   python scripts/export_entidades_gold.py <slug> [--top 60]
Salida: annotation/gold_entidades/<slug>.csv
"""

from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from src import manifiesto
from src.pipeline.entity_discovery import (
    _GENERICOS,
    _TIPOS_ACTOR,
    _es_actor,
    descubrir_entidades,
)
from src.schemas import Documento

log = logging.getLogger(__name__)

CAMPOS = [
    "nombre",
    "tipo",
    "n_docs",
    "n_menciones",
    "alias",
    "rank_crudo",
    "retenida",
    "es_actor_gold",
    "tipo_correcto",
    "nombre_canonico",
    "notas",
]
SALIDA_DIR = Path("annotation/gold_entidades")
_TODOS = frozenset({"PER", "ORG", "LOC", "MISC"})


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


def exportar(slug: str, *, top: int = 60) -> tuple[Path, int, int]:
    corpus = manifiesto.corpus_path(slug)
    if not corpus.exists():
        raise FileNotFoundError(
            f"No existe {corpus}. Corre antes: python scripts/precompute_tema.py {slug}"
        )
    docs = _docs(slug)
    # CRUDO: todos los tipos, sin denylist; pedimos de más (top*3) para ver ruido.
    crudo = descubrir_entidades(
        docs, top_n=top * 3, tipos=_TODOS, excluir=set(), enriquecer_wikidata=False
    )
    log.info("entidades crudas descubiertas: %d", len(crudo))

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    salida = SALIDA_DIR / f"{slug}.csv"
    n_ret = 0
    with open(salida, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for rank, node in enumerate(crudo[:top], 1):
            info = {"tipo": node.tipo, "nombre": node.nombre}
            retenida = _es_actor(info, _TIPOS_ACTOR, _GENERICOS)
            n_ret += int(retenida)
            w.writerow(
                {
                    "nombre": node.nombre,
                    "tipo": node.tipo,
                    "n_docs": node.n_docs,
                    "n_menciones": node.n_menciones,
                    "alias": " | ".join(node.alias[:6]),
                    "rank_crudo": rank,
                    "retenida": int(retenida),
                    "es_actor_gold": "",
                    "tipo_correcto": "",
                    "nombre_canonico": "",
                    "notas": "",
                }
            )
    return salida, min(top, len(crudo)), n_ret


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    os.environ.setdefault("SPACY_NER_MODEL", "es_core_news_md")
    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    top = 60
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    if not args:
        print("Uso: python scripts/export_entidades_gold.py <slug> [--top 60]")
        raise SystemExit(1)

    ruta, k, n_ret = exportar(args[0], top=top)
    print(f"\nExportadas {k} entidades ({n_ret} retenidas por el filtro) -> {ruta}")
    print("Completa es_actor_gold (1/0), tipo_correcto y nombre_canonico, luego:")
    print(f"  python -m eval.entities {ruta}")
