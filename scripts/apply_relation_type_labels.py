"""Aplica etiquetas humanas de clusters inducidos al grafo DuckDB."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from src import manifiesto
from src.pipeline.relation_typing import aplicar_etiquetas, etiquetas_desde_csv
from src.storage import KnowledgeGraph


def _leer_asignaciones(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def aplicar(
    slug: str, *, labels: Path | None = None, assignments: Path | None = None
) -> int:
    out_dir = manifiesto.salidas_dir(slug)
    labels = labels or out_dir / "relation_type_clusters.csv"
    assignments = assignments or out_dir / "relation_type_assignments.csv"
    if not labels.exists():
        raise FileNotFoundError(
            f"No existe {labels}. Ejecuta export_relation_type_clusters.py primero."
        )
    if not assignments.exists():
        raise FileNotFoundError(
            f"No existe {assignments}. Ejecuta export_relation_type_clusters.py primero."
        )

    etiquetas = etiquetas_desde_csv(labels)
    rows = _leer_asignaciones(assignments)
    with KnowledgeGraph(slug) as grafo:
        n = aplicar_etiquetas(grafo, rows, etiquetas)

    with open(assignments, "w", encoding="utf-8", newline="") as f:
        campos = (
            list(rows[0].keys())
            if rows
            else ["relation_id", "cluster_id", "predicado", "tipo_label"]
        )
        if "tipo_label" not in campos:
            campos.append("tipo_label")
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for row in rows:
            row = dict(row)
            row["tipo_label"] = etiquetas.get(row.get("cluster_id", ""), "")
            w.writerow(row)
    return n


def main() -> None:
    p = argparse.ArgumentParser(
        description="Persiste tipos inducidos en relations.tipo"
    )
    p.add_argument("slug")
    p.add_argument("--labels", type=Path, default=None)
    p.add_argument("--assignments", type=Path, default=None)
    args = p.parse_args()
    n = aplicar(args.slug, labels=args.labels, assignments=args.assignments)
    print(f"Relaciones actualizadas: {n}")


if __name__ == "__main__":
    main()
