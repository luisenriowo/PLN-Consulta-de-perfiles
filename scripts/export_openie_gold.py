"""Exporta una muestra de relaciones abiertas para gold OpenIE/tipado.

El anotador completa:
  - triple_valido_gold: 1 si la arista expresa relación entre ambas entidades.
  - predicado_ok_gold: 1 si el predicado captura el vínculo expresado.
  - tipo_gold: etiqueta humana del tipo emergente/final.
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from src import manifiesto
from src.storage import KnowledgeGraph


CAMPOS = [
    "relation_id",
    "cluster_id",
    "entity_a",
    "entity_b",
    "predicado",
    "oracion",
    "doc_id",
    "fecha",
    "tipo_sugerido",
    "triple_valido_gold",
    "predicado_ok_gold",
    "tipo_gold",
    "notas",
]


def _cluster_por_relacion(slug: str) -> dict[str, str]:
    path = manifiesto.salidas_dir(slug) / "relation_type_assignments.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {r["relation_id"]: r["cluster_id"] for r in csv.DictReader(f)}


def exportar(slug: str, *, n: int = 120, semilla: int = 42) -> tuple[Path, int]:
    cluster_map = _cluster_por_relacion(slug)
    filas: list[dict] = []
    with KnowledgeGraph(slug, read_only=True) as grafo:
        for rel in grafo.relations():
            predicado = (rel.get("predicado") or "").strip()
            if not predicado:
                continue
            ev = grafo.evidencia(int(rel["id"]))
            filas.append(
                {
                    "relation_id": str(rel["id"]),
                    "cluster_id": cluster_map.get(str(rel["id"]), ""),
                    "entity_a": rel.get("origen_nombre") or rel["origen_id"],
                    "entity_b": rel.get("destino_nombre") or rel["destino_id"],
                    "predicado": predicado,
                    "oracion": (ev.get("pasajes") or [""])[0],
                    "doc_id": (ev.get("fuentes") or [""])[0],
                    "fecha": rel["fecha"],
                    "tipo_sugerido": rel.get("tipo") or "",
                    "triple_valido_gold": "",
                    "predicado_ok_gold": "",
                    "tipo_gold": "",
                    "notas": "",
                }
            )

    por_estrato: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        estrato = fila["cluster_id"] or fila["predicado"]
        por_estrato[estrato].append(fila)

    rng = random.Random(semilla)
    por_cada = max(1, n // max(1, len(por_estrato)))
    seleccion: list[dict] = []
    for grupo in por_estrato.values():
        grupo = list(grupo)
        rng.shuffle(grupo)
        seleccion.extend(grupo[:por_cada])
    rng.shuffle(seleccion)
    seleccion = seleccion[:n]

    out_dir = Path("annotation/gold_relaciones_abiertas")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slug}.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(seleccion)
    return out, len(seleccion)


def main() -> None:
    p = argparse.ArgumentParser(description="Exporta gold de OpenIE y tipado inducido")
    p.add_argument("slug")
    p.add_argument("--n", type=int, default=120)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    out, k = exportar(args.slug, n=args.n, semilla=args.seed)
    print(f"Exportadas {k} filas -> {out}")


if __name__ == "__main__":
    main()
