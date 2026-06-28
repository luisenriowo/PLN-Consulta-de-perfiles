"""Evaluación de tipado inducido de relaciones.

Compara `tipo_sugerido` contra `tipo_gold` en el gold exportado para OpenIE. La
taxonomía puede ser emergente: las etiquetas se toman del propio CSV.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict


def cargar(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        r
        for r in rows
        if (r.get("tipo_gold") or "").strip() and (r.get("tipo_sugerido") or "").strip()
    ]


def evaluar(path: str) -> dict:
    rows = cargar(path)
    confusion: dict[tuple[str, str], int] = {}
    correctos = 0
    for r in rows:
        gold = r["tipo_gold"].strip()
        pred = r["tipo_sugerido"].strip()
        confusion[(gold, pred)] = confusion.get((gold, pred), 0) + 1
        if gold == pred:
            correctos += 1

    tipos = sorted({g for g, _ in confusion} | {p for _, p in confusion})
    por_tipo: dict[str, dict] = {}
    for tipo in tipos:
        tp = confusion.get((tipo, tipo), 0)
        fp = sum(v for (g, p), v in confusion.items() if p == tipo and g != tipo)
        fn = sum(v for (g, p), v in confusion.items() if g == tipo and p != tipo)
        support = sum(v for (g, _), v in confusion.items() if g == tipo)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        por_tipo[tipo] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    con_soporte = [t for t in tipos if por_tipo[t]["support"]]
    macro_f1 = (
        sum(por_tipo[t]["f1"] for t in con_soporte) / len(con_soporte)
        if con_soporte
        else 0.0
    )
    return {
        "n": len(rows),
        "accuracy": correctos / len(rows) if rows else 0.0,
        "macro_f1": macro_f1,
        "por_tipo": por_tipo,
        "confusion": confusion,
        "coherencia_clusters": coherencia_clusters(rows),
    }


def coherencia_clusters(rows: list[dict]) -> dict:
    """Pureza promedio de clusters contra tipo_gold en filas anotadas."""
    por_cluster: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        cid = (r.get("cluster_id") or "").strip()
        gold = (r.get("tipo_gold") or "").strip()
        if cid and gold:
            por_cluster[cid].append(gold)
    if not por_cluster:
        return {"n_clusters": 0, "pureza_media": 0.0, "pureza_ponderada": 0.0}
    purezas = []
    total = 0
    aciertos_mayoria = 0
    for labels in por_cluster.values():
        c = Counter(labels)
        mayoria = c.most_common(1)[0][1]
        purezas.append(mayoria / len(labels))
        total += len(labels)
        aciertos_mayoria += mayoria
    return {
        "n_clusters": len(por_cluster),
        "pureza_media": sum(purezas) / len(purezas),
        "pureza_ponderada": aciertos_mayoria / total if total else 0.0,
    }


def formato(m: dict) -> str:
    out = [
        f"== Tipado inducido ==  n={m['n']}  accuracy={m['accuracy']:.3f}  macro-F1={m['macro_f1']:.3f}",
        f"  clusters: n={m['coherencia_clusters']['n_clusters']} "
        f"pureza_media={m['coherencia_clusters']['pureza_media']:.3f} "
        f"pureza_pond={m['coherencia_clusters']['pureza_ponderada']:.3f}",
        f"  {'tipo':18s} {'P':>6s} {'R':>6s} {'F1':>6s} {'sup':>5s}",
    ]
    for tipo, d in m["por_tipo"].items():
        if d["support"] == 0:
            continue
        out.append(
            f"  {tipo:18s} {d['precision']:6.2f} {d['recall']:6.2f} "
            f"{d['f1']:6.2f} {d['support']:5d}"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    import sys

    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(
            "Uso: python -m eval.relation_typing annotation/gold_relaciones_abiertas/<slug>.csv"
        )
        raise SystemExit(1)
    print(formato(evaluar(argv[0])))


if __name__ == "__main__":
    main()
