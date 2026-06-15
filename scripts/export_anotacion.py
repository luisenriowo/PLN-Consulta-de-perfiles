"""Exporta el corpus a un spreadsheet para que los anotadores arranquen el gold.

Una fila por NOTA (no por evento del sistema: anotar desde las notas evita la
circularidad, CLAUDE.md / protocol.md §0). Incluye las notas donde Humala
aparece (protagonista + solo_mencionado), para que el humano aplique su propio
juicio de protagonismo/saliencia; excluye `no_mencionado` (Humala ausente).

Genera:
  - data/corpus_anotacion.csv      → las notas a leer (UTF-8 BOM, abre en Excel).
  - annotation/gold_template.csv   → plantilla vacía del gold (formato §4).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CORPUS = Path("data/corpus_humala.parquet")
SALIDA_NOTAS = Path("data/corpus_anotacion.csv")
SALIDA_TEMPLATE = Path("annotation/gold_template.csv")


def main() -> None:
    df = pd.read_parquet(CORPUS)
    df = df[df["clase_protagonismo"] != "no_mencionado"].copy()

    lineas = df["texto"].str.split("\n")
    df["titulo"] = lineas.str[0]
    df["lead"] = lineas.str[1].fillna("")

    cols = ["doc_id", "fecha_pub", "titulo", "lead", "url", "clase_protagonismo"]
    out = df[cols].sort_values(
        ["clase_protagonismo", "fecha_pub"], ascending=[True, True]
    )
    # protagonista primero (orden alfabético inverso pone 'protagonista' antes
    # que 'solo_mencionado'): re-ordenamos explícito por prioridad.
    orden = {"protagonista": 0, "solo_mencionado": 1}
    out = (
        out.assign(_p=out["clase_protagonismo"].map(orden))
        .sort_values(["_p", "fecha_pub"])
        .drop(columns="_p")
    )

    SALIDA_NOTAS.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(SALIDA_NOTAS, index=False, encoding="utf-8-sig")

    # Plantilla del gold (columnas de protocol.md §4), vacía salvo cabecera.
    template = pd.DataFrame(
        columns=["fecha", "descripcion", "fuentes", "tipo", "saliencia"]
    )
    SALIDA_TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(SALIDA_TEMPLATE, index=False, encoding="utf-8-sig")

    print(f"notas exportadas: {len(out)}")
    print(f"  por clase: {out['clase_protagonismo'].value_counts().to_dict()}")
    print(f"  rango: {out['fecha_pub'].min()} … {out['fecha_pub'].max()}")
    print(f"escrito {SALIDA_NOTAS}")
    print(f"escrito {SALIDA_TEMPLATE}")


if __name__ == "__main__":
    main()
