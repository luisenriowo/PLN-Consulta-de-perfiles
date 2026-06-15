"""Corre las condiciones de generación SIN LLM (B0, B1) sobre los eventos salientes.

Reconstruye los EventCluster (cluster → salience) y aplica cada condición,
mostrando la comparación y guardando las salidas en data/salidas/<cond>.json
(list[TimelineEntry]). Sistema/Ablación se añaden cuando haya API key.

Uso:  python scripts/run_generation.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.generation import _llm
from src.generation.ablacion import Ablacion
from src.generation.b0_lead import B0Lead
from src.generation.b1_extractive import B1Extractive
from src.generation.sistema_rag import SistemaRAG
from src.pipeline import cluster, salience
from src.schemas import Documento

CORPUS = Path("data/corpus_humala.parquet")
SALIDAS = Path("data/salidas")

# B0/B1 no usan LLM. Sistema/Ablación sí: solo se añaden si hay API key.
CONDICIONES = [B0Lead(), B1Extractive()]
if _llm.disponible():
    CONDICIONES += [SistemaRAG(), Ablacion()]


def cargar_protagonistas() -> list[Documento]:
    df = pd.read_parquet(CORPUS)
    df = df[df["humala_protagonista"]]
    return [
        Documento(
            doc_id=r.doc_id, fuente=r.fuente, url=r.url,
            fecha_pub=date.fromisoformat(r.fecha_pub), texto=r.texto,
        )
        for r in df.itertuples()
    ]


def main() -> None:
    docs = cargar_protagonistas()
    clusters = cluster.cluster_events(docs, umbral=cluster.UMBRAL_DEFECTO)
    salientes = salience.select_salient(clusters)
    print(f"docs={len(docs)}  eventos={len(clusters)}  salientes={len(salientes)}")

    nombres = [c.name for c in CONDICIONES]
    print(f"condiciones: {nombres}")
    salidas = {cond.name: cond.generate(salientes) for cond in CONDICIONES}

    for nombre in nombres:
        entries = salidas[nombre]
        print(f"\n== {nombre} ({len(entries)} entradas) ==")
        for e in entries[:4]:
            print(f"  {e.fecha} | {e.resumen[:95]}")

    if _llm.disponible():
        print(f"\n== COSTO LLM ==\n  {_llm.costo()}")

    SALIDAS.mkdir(parents=True, exist_ok=True)
    for nombre, entries in salidas.items():
        ruta = SALIDAS / f"{nombre}.json"
        ruta.write_text(
            json.dumps(
                [{**e.model_dump(), "fecha": e.fecha.isoformat()} for e in entries],
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nguardado {ruta} ({len(entries)} entradas)")


if __name__ == "__main__":
    main()
