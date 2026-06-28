"""Evaluación — Resolución de entidades (Fase 2: calidad del grafo de actores).

Mide la calidad del descubrimiento/agrupación de entidades contra un gold humano.
Un grafo solo vale lo que vale su deduplicación de nodos: si el top está
contaminado de ruido (LOC genéricos, fragmentos) o un mismo actor aparece
partido en varios nodos, el análisis (centralidad, comunidades) miente.

Métricas (sobre las filas etiquetadas del gold):
  - actor_precision: de las entidades RETENIDAS por el filtro, fracción que son
    actores reales (es_actor_gold=1). Mide cuánto ruido sobrevive.
  - actor_recall:    de los actores reales (es_actor_gold=1), fracción RETENIDA.
    Mide cuántos actores reales descarta el filtro por error.
  - type_accuracy:   de las filas con `tipo_correcto`, fracción con tipo == correcto.
  - splits:          formas canónicas (nombre_canonico) que aparecen en >1 fila →
    el mismo actor partido en varios nodos (fallo de agrupación).

Formato del gold (CSV). Columnas:
  nombre, tipo, n_docs, retenida,   # las llena el export (retenida = sobrevivió el filtro)
  es_actor_gold,                    # humano: 1/0
  tipo_correcto,                    # humano: PER|ORG|LOC|MISC (opcional)
  nombre_canonico                   # humano: nombre verdadero del actor (opcional, para splits)

Las filas con `es_actor_gold` vacío se omiten. Se valida con verdades conocidas
(scripts/test_entities.py) ANTES del gold real.

Uso:  python -m eval.entities annotation/gold_entidades/<slug>.csv
"""

from __future__ import annotations

import csv
from collections import Counter


def _verdadero(v: str | None) -> bool:
    return str(v or "").strip() in {"1", "true", "True", "sí", "si"}


def cargar_gold(path) -> list[dict]:
    """Filas del gold con `es_actor_gold` no vacío (etiquetadas)."""
    with open(path, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    etiquetadas = [r for r in filas if str(r.get("es_actor_gold") or "").strip()]
    if not etiquetadas:
        raise ValueError(
            f"{path}: 0 filas etiquetadas (la columna 'es_actor_gold' está vacía)."
        )
    return etiquetadas


def evaluar(filas: list[dict]) -> dict:
    """Computa las métricas de calidad de entidades sobre filas etiquetadas."""
    n = len(filas)
    retenidas = [r for r in filas if _verdadero(r.get("retenida"))]
    actores = [r for r in filas if _verdadero(r.get("es_actor_gold"))]

    # Precision: de las retenidas, cuántas son actores reales.
    actor_precision = (
        sum(_verdadero(r.get("es_actor_gold")) for r in retenidas) / len(retenidas)
        if retenidas
        else 0.0
    )
    # Recall del filtro: de los actores reales, cuántos fueron retenidos.
    actor_recall = (
        sum(_verdadero(r.get("retenida")) for r in actores) / len(actores)
        if actores
        else 0.0
    )
    # Exactitud de tipo (solo filas con tipo_correcto anotado).
    con_tipo = [r for r in filas if str(r.get("tipo_correcto") or "").strip()]
    type_accuracy = (
        sum(
            (r.get("tipo") or "").strip() == (r.get("tipo_correcto") or "").strip()
            for r in con_tipo
        )
        / len(con_tipo)
        if con_tipo
        else None
    )
    # Splits: nombre_canonico que aparece en >1 fila etiquetada.
    canon = Counter(
        (r.get("nombre_canonico") or "").strip()
        for r in filas
        if (r.get("nombre_canonico") or "").strip()
    )
    splits = {nombre: c for nombre, c in canon.items() if c > 1}

    f1 = (
        2 * actor_precision * actor_recall / (actor_precision + actor_recall)
        if (actor_precision + actor_recall)
        else 0.0
    )
    return {
        "n": n,
        "n_retenidas": len(retenidas),
        "n_actores": len(actores),
        "actor_precision": actor_precision,
        "actor_recall": actor_recall,
        "actor_f1": f1,
        "type_accuracy": type_accuracy,
        "splits": splits,
    }


def formato(m: dict) -> str:
    ta = "n/a" if m["type_accuracy"] is None else f"{m['type_accuracy']:.3f}"
    out = [
        f"== Resolución de entidades ==  n={m['n']}  retenidas={m['n_retenidas']}  "
        f"actores_gold={m['n_actores']}",
        f"  actor_precision (ruido en lo retenido): {m['actor_precision']:.3f}",
        f"  actor_recall    (actores descartados):  {m['actor_recall']:.3f}",
        f"  actor_F1:                               {m['actor_f1']:.3f}",
        f"  type_accuracy:                          {ta}",
    ]
    if m["splits"]:
        out.append(f"  splits (actor partido en varios nodos): {m['splits']}")
    else:
        out.append("  splits: ninguno detectado")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    import sys

    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Uso: python -m eval.entities <gold.csv>")
        raise SystemExit(1)
    filas = cargar_gold(argv[0])
    print(f"Gold: {len(filas)} entidades etiquetadas ({argv[0]})\n")
    print(formato(evaluar(filas)))


if __name__ == "__main__":
    main()
