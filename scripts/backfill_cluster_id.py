"""Backfill de `cluster_id` en las salidas ya generadas (SIN llamar al LLM).

Las salidas en data/salidas/*.json se generaron antes de que TimelineEntry
llevara `cluster_id`. Este script lo añade mapeando cada entrada a su cluster
por el conjunto de `fuentes` (único por cluster), usando el cluster_id ya
persistido en data/eventos_humala.parquet. No regenera texto ni recalcula nada.

A partir de ahora las condiciones emiten `cluster_id` nativo, así que esto es
una migración de una sola vez para los archivos existentes.

Uso:  python scripts/backfill_cluster_id.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

EVENTOS = Path("data/eventos_humala.parquet")
SALIDAS = Path("data/salidas/humala")  # layout por-figura


def main() -> None:
    df = pd.read_parquet(EVENTOS)
    # frozenset(fuentes) -> cluster_id  (las fuentes identifican el cluster)
    por_fuentes = {
        frozenset(str(r["fuentes"]).split(",")): r["cluster_id"]
        for r in df.to_dict(orient="records")
    }

    for ruta in sorted(SALIDAS.glob("*.json")):
        entradas = json.loads(ruta.read_text(encoding="utf-8"))
        ok = sin_match = 0
        for e in entradas:
            cid = por_fuentes.get(frozenset(e.get("fuentes", [])))
            e["cluster_id"] = cid
            if cid:
                ok += 1
            else:
                sin_match += 1
        ruta.write_text(
            json.dumps(entradas, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  {ruta.name}: {ok} con cluster_id, {sin_match} sin match")


if __name__ == "__main__":
    main()
