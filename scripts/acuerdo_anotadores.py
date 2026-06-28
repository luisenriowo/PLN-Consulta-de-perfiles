"""Acuerdo inter-anotador para los golds (entidades / relaciones).

Convierte "mi criterio" en "criterio con acuerdo inter-anotador" — la diferencia
entre un gold defendible y uno que no lo es (ver annotation/GUIA_ANOTACION.md).

Dos modos:

  1) Generar una MUESTRA EN BLANCO para un segundo anotador (B):
       python scripts/acuerdo_anotadores.py --blank annotation/gold_relaciones/roberto-sanchez.csv \
              --n 30 --col tipo_gold
     Crea <stem>_muestraB.csv con N filas (semilla fija), la columna objetivo
     vaciada y una columna `fila_id` para alinear después. B la etiqueta SIN ver
     las etiquetas de A.

  2) Medir ACUERDO entre A (gold completo) y B (muestra etiquetada):
       python scripts/acuerdo_anotadores.py annotation/gold_relaciones/roberto-sanchez.csv \
              annotation/gold_relaciones/roberto-sanchez_muestraB.csv --col tipo_gold
     Reporta % de acuerdo, κ de Cohen y las discrepancias.

`--col` por defecto `tipo_gold` (relaciones). Para entidades usa
`--col es_actor_gold` (o `tipo_correcto`).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd


def _arg(flag: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def blank(gold_path: str, *, n: int, col: str, seed: int = 7) -> Path:
    df = pd.read_csv(gold_path)
    n = min(n, len(df))
    muestra = df.sample(n=n, random_state=seed).copy()
    muestra.insert(0, "fila_id", muestra.index)
    muestra[col] = ""  # vaciar la columna objetivo
    out = Path(gold_path).with_name(Path(gold_path).stem + "_muestraB.csv")
    muestra.to_csv(out, index=False, encoding="utf-8")
    return out


def _kappa(a: list[str], b: list[str]) -> float:
    """κ de Cohen sobre dos secuencias de etiquetas alineadas."""
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    clases = set(ca) | set(cb)
    pe = sum((ca.get(c, 0) / n) * (cb.get(c, 0) / n) for c in clases)
    return (po - pe) / (1 - pe) if pe != 1 else 1.0


def acuerdo(a_path: str, b_path: str, *, col: str) -> None:
    a = pd.read_csv(a_path)
    b = pd.read_csv(b_path)
    if "fila_id" not in b.columns:
        print("ERROR: el archivo B no tiene columna 'fila_id' (genéralo con --blank).")
        raise SystemExit(1)

    pares: list[tuple[int, str, str]] = []
    for _, rb in b.iterrows():
        val_b = str(rb.get(col) or "").strip()
        if not val_b:
            continue  # B no etiquetó esa fila
        idx = int(rb["fila_id"])
        val_a = str(a.iloc[idx][col] or "").strip()
        pares.append((idx, val_a, val_b))

    if not pares:
        print("No hay filas etiquetadas por B para comparar.")
        raise SystemExit(1)

    la = [p[1] for p in pares]
    lb = [p[2] for p in pares]
    n = len(pares)
    acuerdos = sum(x == y for x, y in zip(la, lb))
    po = acuerdos / n
    k = _kappa(la, lb)

    print(f"Acuerdo inter-anotador sobre '{col}'  (n={n})")
    print(f"  % de acuerdo:  {po:.3f}  ({acuerdos}/{n})")
    print(f"  kappa de Cohen: {k:.3f}  ({_interpretar_kappa(k)})")
    disc = [p for p in pares if p[1] != p[2]]
    if disc:
        print(f"\n  Discrepancias ({len(disc)}):")
        for idx, va, vb in disc:
            print(f"    fila {idx:3d}: A={va:14s} B={vb}")


def _interpretar_kappa(k: float) -> str:
    if k < 0.0:
        return "peor que azar"
    if k < 0.20:
        return "leve"
    if k < 0.40:
        return "aceptable"
    if k < 0.60:
        return "moderado"
    if k < 0.80:
        return "sustancial"
    return "casi perfecto"


def main() -> None:
    col = _arg("--col", "tipo_gold")
    if "--blank" in sys.argv:
        gold = _arg("--blank")
        n = int(_arg("--n", "30"))
        out = blank(gold, n=n, col=col)
        print(f"Muestra en blanco para anotador B -> {out}")
        print(f"B debe completar la columna '{col}' (sin ver el gold A), luego:")
        print(f"  python scripts/acuerdo_anotadores.py {gold} {out} --col {col}")
        return

    # Posicionales = args sin '--' y que no sean el valor que sigue a un flag.
    valores_flag = {
        sys.argv[sys.argv.index(f) + 1] for f in ("--col", "--n") if f in sys.argv
    }
    posicionales = [
        a for a in sys.argv[1:] if not a.startswith("--") and a not in valores_flag
    ]
    if len(posicionales) != 2:
        print(__doc__)
        raise SystemExit(1)
    acuerdo(posicionales[0], posicionales[1], col=col)


if __name__ == "__main__":
    main()
