"""Re-clasifica el protagonismo del corpus con la regla estricta, sin re-scrapear.

Lee data/corpus_humala.parquet (que ya guarda las entidades enlazadas),
reconstruye los Documento, aplica `pipeline.protagonism.clasificar` y reescribe
los flags. Reporta el antes/después.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from src.pipeline.protagonism import clasificar
from src.schemas import Documento, EntidadMencion

CORPUS = Path("data/corpus_humala.parquet")


def _doc(row) -> Documento:
    ents = [EntidadMencion(**e) for e in json.loads(row.entidades)]
    return Documento(
        doc_id=row.doc_id,
        fuente=row.fuente,
        url=row.url,
        fecha_pub=date.fromisoformat(row.fecha_pub),
        texto=row.texto,
        entidades=ents,
    )


def main() -> None:
    df = pd.read_parquet(CORPUS)
    antes = Counter(df["clase_protagonismo"])
    nuevas = [clasificar(_doc(r)) for r in df.itertuples()]
    df["clase_protagonismo"] = nuevas
    df["humala_protagonista"] = df["clase_protagonismo"] == "protagonista"
    despues = Counter(nuevas)

    print("clase           antes  ->  después")
    for c in ("protagonista", "solo_mencionado", "no_mencionado"):
        print(f"  {c:16} {antes.get(c, 0):4d}  ->  {despues.get(c, 0):4d}")

    # Notas que dejaron de ser protagonistas (las que el guard de familia sacó)
    df_old = pd.read_parquet(CORPUS)
    perdidas = df_old[(df_old["humala_protagonista"]) & (~df["humala_protagonista"])]
    print(f"\nreclasificadas fuera de protagonista: {len(perdidas)}")
    for t in perdidas["texto"].str.split("\n").str[0].head(8):
        print("  -", t[:85])

    df.to_parquet(CORPUS, index=False)
    print(f"\nreescrito {CORPUS}")


if __name__ == "__main__":
    main()
