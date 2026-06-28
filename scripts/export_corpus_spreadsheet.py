"""Exporta el corpus a spreadsheet para anotacion humana.

Entrada:
  data/corpus_humala.parquet

Salida:
  data/corpus_humala_anotacion.xlsx
  data/corpus_humala_anotacion.csv

Uso:
  python scripts/export_corpus_spreadsheet.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CORPUS = Path("data/corpus_humala.parquet")
SALIDA_XLSX = Path("data/corpus_humala_anotacion.xlsx")
SALIDA_CSV = Path("data/corpus_humala_anotacion.csv")


def _partes_texto(texto: str) -> tuple[str, str]:
    """Devuelve titulo y lead desde el formato titulo\\nlead\\ncuerpo."""
    lineas = [linea.strip() for linea in str(texto).splitlines() if linea.strip()]
    titulo = lineas[0] if lineas else ""
    lead = lineas[1] if len(lineas) > 1 else ""
    return titulo, lead


def construir_spreadsheet(df: pd.DataFrame) -> pd.DataFrame:
    """Arma una tabla estable y directa para anotadores."""
    filas = []
    for row in df.to_dict(orient="records"):
        titulo, lead = _partes_texto(row["texto"])
        filas.append(
            {
                "doc_id": row["doc_id"],
                "fecha_pub": row["fecha_pub"],
                "titulo": titulo,
                "url": row["url"],
                "lead": lead,
                "fuente": row["fuente"],
                "queries": row["queries"],
                "clase_protagonismo": row["clase_protagonismo"],
                "humala_protagonista": bool(row["humala_protagonista"]),
                "anotar_en_gold": "",
                "fecha_evento_gold": "",
                "resumen_evento_gold": "",
                "notas_anotador": "",
            }
        )

    out = pd.DataFrame(filas)
    return out.sort_values(
        ["humala_protagonista", "fecha_pub", "doc_id"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def main() -> None:
    if not CORPUS.exists():
        raise FileNotFoundError(
            f"No existe {CORPUS}. Ejecuta primero: python scripts/build_corpus.py"
        )

    df = pd.read_parquet(CORPUS)
    salida = construir_spreadsheet(df)

    SALIDA_XLSX.parent.mkdir(parents=True, exist_ok=True)
    salida.to_excel(SALIDA_XLSX, index=False, sheet_name="corpus")
    salida.to_csv(SALIDA_CSV, index=False, encoding="utf-8-sig")

    protagonistas = int(salida["humala_protagonista"].sum())
    print(f"filas exportadas: {len(salida)}")
    print(f"protagonistas primero: {protagonistas}")
    print(f"generado: {SALIDA_XLSX}")
    print(f"generado: {SALIDA_CSV}")


if __name__ == "__main__":
    main()
