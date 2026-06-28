"""Exporta clusters inducidos de predicados para etiquetado humano.

Requiere un grafo abierto ya construido (`scripts/build_open_graph.py`). No llama
al LLM: agrupa `relations.predicado` con embeddings y deja dos CSVs:
  - data/salidas/<slug>/relation_type_clusters.csv       (anotar tipo_label)
  - data/salidas/<slug>/relation_type_assignments.csv    (relation_id→cluster)
"""

from __future__ import annotations

import argparse
import csv
import json

from src import manifiesto
from src.pipeline.relation_typing import (
    asignaciones,
    cargar_predicados,
    clusterizar_predicados,
)
from src.storage import KnowledgeGraph


def exportar(slug: str, *, threshold: float = 0.10) -> tuple[int, int]:
    out_dir = manifiesto.salidas_dir(slug)
    out_dir.mkdir(parents=True, exist_ok=True)
    clusters_path = out_dir / "relation_type_clusters.csv"
    assignments_path = out_dir / "relation_type_assignments.csv"

    with KnowledgeGraph(slug, read_only=True) as grafo:
        instancias = cargar_predicados(grafo)
        clusters = clusterizar_predicados(instancias, distance_threshold=threshold)

    with open(clusters_path, "w", encoding="utf-8", newline="") as f:
        campos = ["cluster_id", "n", "predicados_top", "ejemplos", "tipo_label"]
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for cluster in clusters:
            w.writerow(
                {
                    "cluster_id": cluster.cluster_id,
                    "n": cluster.n,
                    "predicados_top": json.dumps(
                        cluster.predicados_top, ensure_ascii=False
                    ),
                    "ejemplos": json.dumps(cluster.ejemplos, ensure_ascii=False),
                    "tipo_label": "",
                }
            )

    rows = asignaciones(clusters)
    with open(assignments_path, "w", encoding="utf-8", newline="") as f:
        campos = [
            "relation_id",
            "cluster_id",
            "predicado",
            "origen",
            "destino",
            "fecha",
            "tipo_label",
        ]
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for row in rows:
            row = dict(row)
            row["tipo_label"] = ""
            w.writerow(row)

    return len(clusters), len(rows)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Exporta clusters inducidos de relaciones abiertas"
    )
    p.add_argument("slug")
    p.add_argument("--threshold", type=float, default=0.10)
    args = p.parse_args()
    n_clusters, n_rel = exportar(args.slug, threshold=args.threshold)
    out_dir = manifiesto.salidas_dir(args.slug)
    print(f"clusters={n_clusters} relaciones={n_rel}")
    print(f"Anota: {out_dir / 'relation_type_clusters.csv'}")
    print(f"Luego aplica: python scripts/apply_relation_type_labels.py {args.slug}")


if __name__ == "__main__":
    main()
