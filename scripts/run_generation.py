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

from src.generation.b0_lead import B0Lead
from src.generation.b1_extractive import B1Extractive
from src.pipeline import cluster, salience
from src.schemas import Documento

CORPUS = Path("data/corpus_humala.parquet")
SALIDAS = Path("data/salidas")
CONDICIONES = [B0Lead(), B1Extractive()]


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

    salidas = {cond.name: cond.generate(salientes) for cond in CONDICIONES}

    print("\n== COMPARACIÓN B0 (lead) vs B1 (extractivo) ==")
    for i, c in enumerate(salientes):
        b0 = salidas["b0_lead"][i].resumen
        b1 = salidas["b1_extractive"][i].resumen
        marca = "  =" if b0 == b1 else "  ≠"
        print(f"\n{c.fecha_normalizada} [{len(c.fuentes)}n]{marca}")
        print(f"  B0: {b0[:100]}")
        print(f"  B1: {b1[:100]}")

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
