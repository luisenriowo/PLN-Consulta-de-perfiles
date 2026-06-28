"""Evaluación — Métricas (CLAUDE.md §7).

- Date F1: selección de fechas correctas vs gold (con tolerancia en días).
- ROUGE por alineamiento: calidad de contenido sobre los pares alineados.
- Tasa de alucinación (métrica estrella): proporción de `TimelineEntry` cuyo
  `resumen` no está respaldado por el texto de sus `fuentes`. El juez de
  "respaldo" es INYECTABLE (`verificador`): por defecto NLI/entailment en
  español (eval/nli.py); puede ser una etiqueta manual o un stub para tests.

La lógica de cada métrica se prueba con un fixture de verdades conocidas
(scripts/test_eval.py) ANTES de tener el gold real.
"""

from __future__ import annotations

from collections.abc import Callable

from eval.align import alinear, sim_rouge1
from src.schemas import TimelineEntry

rouge_1 = sim_rouge1  # mismo cálculo (F1 de unigramas)


# ---------- Date F1 ----------


def date_f1(
    predicho: list[TimelineEntry], gold: list[TimelineEntry], *, tol_dias: int = 0
) -> dict:
    """P/R/F1 sobre las fechas (emparejamiento 1-a-1 dentro de ±tol_dias)."""
    gold_usados: set[int] = set()
    tp = 0
    for p in predicho:
        for j, g in enumerate(gold):
            if j in gold_usados:
                continue
            if abs((p.fecha - g.fecha).days) <= tol_dias:
                gold_usados.add(j)
                tp += 1
                break
    fp, fn = len(predicho) - tp, len(gold) - tp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


# ---------- ROUGE ----------


def _lcs(a: list[str], b: list[str]) -> int:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            dp[i + 1][j + 1] = (
                dp[i][j] + 1 if x == y else max(dp[i][j + 1], dp[i + 1][j])
            )
    return dp[-1][-1]


def rouge_l(cand: str, ref: str) -> float:
    import re

    tc, tr = re.findall(r"\w+", cand.lower()), re.findall(r"\w+", ref.lower())
    if not tc or not tr:
        return 0.0
    largo = _lcs(tc, tr)
    if largo == 0:
        return 0.0
    p, r = largo / len(tc), largo / len(tr)
    return 2 * p * r / (p + r)


def rouge_alineado(pares: list[tuple[TimelineEntry, TimelineEntry]]) -> dict:
    """Media de ROUGE-1 y ROUGE-L sobre los pares (pred.resumen vs gold.resumen)."""
    if not pares:
        return {"rouge1": 0.0, "rougeL": 0.0, "n_pares": 0}
    r1 = sum(rouge_1(p.resumen, g.resumen) for p, g in pares) / len(pares)
    rl = sum(rouge_l(p.resumen, g.resumen) for p, g in pares) / len(pares)
    return {"rouge1": r1, "rougeL": rl, "n_pares": len(pares)}


def rouge_vs_gold(
    predicho: list[TimelineEntry], gold: list[TimelineEntry], *, tol_dias: int = 0
) -> dict:
    """Alinea y devuelve ROUGE medio sobre los pares alineados."""
    return rouge_alineado(alinear(predicho, gold, tol_dias=tol_dias)["pares"])


# ---------- Tasa de alucinación (métrica estrella) ----------


def tasa_alucinacion(
    entries: list[TimelineEntry],
    fuentes_texto: dict[str, str],
    *,
    verificador: Callable[[str, str], bool] | None = None,
) -> dict:
    """Proporción de entradas cuyo `resumen` no está respaldado por sus fuentes.

    `fuentes_texto`: doc_id -> texto fuente. `verificador(resumen, premisa) ->
    bool` decide si el resumen está respaldado; por defecto el juez NLI.
    """
    if verificador is None:
        from eval.nli import respaldado as verificador  # import perezoso (torch)

    no_resp = 0
    detalle: list[tuple[TimelineEntry, bool]] = []
    for e in entries:
        premisa = "\n".join(fuentes_texto.get(f, "") for f in e.fuentes).strip()
        ok = verificador(e.resumen, premisa)
        if not ok:
            no_resp += 1
        detalle.append((e, ok))
    total = len(entries)
    return {
        "tasa": no_resp / total if total else 0.0,
        "no_respaldadas": no_resp,
        "total": total,
        "detalle": detalle,
    }
