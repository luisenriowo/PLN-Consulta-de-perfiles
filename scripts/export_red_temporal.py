"""Exporta un grafo a un JSON compacto para la visualización temporal
(src/app/web/red_temporal.html). Agrega el multigrafo de relaciones abiertas a
nivel de PAR con su actividad mensual, asigna comunidades (Louvain) como
"facciones" y recorta a top-N entidades / top-K pares para que el navegador lo
renderice fluido.

Uso:   python scripts/export_red_temporal.py <slug> [--top-ent 55] [--top-pairs 320]
Salida: src/app/web/red_<slug>.json   (servido por el backend en /red_<slug>.json)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from src import manifiesto
from src.storage import KnowledgeGraph


def _short(nombre: str, tipo: str) -> str:
    n = " ".join(nombre.split())
    if tipo == "PER":
        p = n.split()
        if len(p) >= 2:
            return f"{p[0][0]}. {p[-1]}"
        return n[:16]
    return n if len(n) <= 18 else n[:17] + "…"


def _fac_color(i: int) -> str:
    # hues bien separados (razón áurea) en oklch, saturación/luma fijas
    h = int((i * 0.61803) % 1.0 * 360)
    return f"oklch(0.71 0.13 {h})"


def exportar(slug: str, *, top_ent: int = 55, top_pairs: int = 320) -> Path:
    with KnowledgeGraph(slug, read_only=True) as g:
        ents = g.entities()
        rels = g.relations()
        try:
            comunidades = g.comunidades()  # list[set[entity_id]]
        except Exception:
            comunidades = []

    id2e = {e["entity_id"]: e for e in ents}
    # comunidad por entidad
    ent2com: dict[str, int] = {}
    for i, miembros in enumerate(comunidades or []):
        for eid in miembros:
            ent2com[eid] = i

    # top entidades por n_docs
    ents_top = sorted(ents, key=lambda e: -(e.get("n_docs") or 0))[:top_ent]
    keep = {e["entity_id"] for e in ents_top}

    # agregar pares (no dirigidos) entre entidades retenidas
    pares: dict[tuple, dict] = defaultdict(
        lambda: {"meses": Counter(), "preds": Counter(), "count": 0}
    )
    for r in rels:
        a, b = r["origen_id"], r["destino_id"]
        if a not in keep or b not in keep or a == b:
            continue
        key = (a, b) if a < b else (b, a)
        p = pares[key]
        p["count"] += 1
        p["meses"][str(r["fecha"])[:7]] += 1
        if r.get("predicado"):
            p["preds"][r["predicado"]] += 1

    top = sorted(pares.items(), key=lambda kv: -kv[1]["count"])[:top_pairs]

    usados = set()
    for (a, b), _ in top:
        usados.add(a)
        usados.add(b)

    # --- evidencia + fuentes por par (para "ver fuentes" y "evolución") ---
    import duckdb
    import pandas as pd

    keep_pair = {k for k, _ in top}
    try:
        cdf = pd.read_parquet(
            manifiesto.corpus_path(slug.replace("-", "_")), columns=["doc_id", "url"]
        )
        doc2url = dict(zip(cdf["doc_id"], cdf["url"]))
    except Exception:
        doc2url = {}
    con = duckdb.connect(str(manifiesto.grafo_path(slug)), read_only=True)
    filas = con.execute(
        "SELECT r.origen_id, r.destino_id, CAST(r.fecha AS VARCHAR), r.predicado, "
        "s.doc_id, e.pasaje FROM relations r "
        "LEFT JOIN relation_sources s ON s.relation_id=r.id "
        "LEFT JOIN relation_evidence e ON e.relation_id=r.id"
    ).fetchall()
    con.close()
    pair_occ: dict[tuple, list] = defaultdict(list)
    for o, d, f, p, doc, ev in filas:
        key = (o, d) if o < d else (d, o)
        if key in keep_pair:
            pair_occ[key].append((str(f)[:10], p or "", doc, ev or ""))

    def _evol(key) -> list[dict]:
        # secuencia fechada deduplicada por (mes, predicado), con su fuente.
        seen: dict[tuple, dict] = {}
        for f, pred, doc, ev in sorted(pair_occ.get(key, [])):
            mk = (f[:7], pred)
            if mk not in seen:
                seen[mk] = {
                    "f": f[:7],
                    "p": pred,
                    "doc": doc,
                    "url": doc2url.get(doc, ""),
                    "ev": ev[:160],
                }
        return list(seen.values())[:20]

    # entidades de salida
    entities = []
    for eid in usados:
        e = id2e[eid]
        c = ent2com.get(eid, 0)
        entities.append(
            {
                "id": eid,
                "label": e["nombre"],
                "sl": _short(e["nombre"], e["tipo"]),
                "type": "org" if e["tipo"] == "ORG" else "person",
                "fac": f"c{c}",
                "ndocs": e.get("n_docs") or 0,
            }
        )

    # facciones = comunidades realmente usadas
    facs = {}
    for c in sorted({ent2com.get(e, 0) for e in usados}):
        facs[f"c{c}"] = {"n": f"Comunidad {c + 1}", "c": _fac_color(c)}

    # pares de salida
    meses_all = []
    pairs_out = []
    for (a, b), p in top:
        meses = sorted(p["meses"])
        pred = p["preds"].most_common(1)[0][0] if p["preds"] else "vínculo"
        pairs_out.append(
            {
                "s": a,
                "t": b,
                "count": p["count"],
                "months": meses,
                "pred": pred,
                "evol": _evol((a, b)),
            }
        )
        meses_all += meses

    out = {
        "slug": slug,
        "title": f"Red temporal · {slug}",
        "min_month": min(meses_all) if meses_all else "2021-01",
        "max_month": max(meses_all) if meses_all else "2021-12",
        "facs": facs,
        "entities": entities,
        "pairs": pairs_out,
    }
    destino = Path("src/app/web") / f"red_{slug}.json"
    destino.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(
        f"[OK] {destino}  entidades={len(entities)} pares={len(pairs_out)} "
        f"facciones={len(facs)} rango={out['min_month']}..{out['max_month']}"
    )
    return destino


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Exporta grafo a JSON para la viz temporal")
    p.add_argument("slug")
    p.add_argument("--top-ent", type=int, default=55)
    p.add_argument("--top-pairs", type=int, default=320)
    a = p.parse_args()
    exportar(a.slug, top_ent=a.top_ent, top_pairs=a.top_pairs)
