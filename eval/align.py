"""Evaluación — Alineamiento predicho ↔ gold (CLAUDE.md §4 eval/).

Empareja `TimelineEntry` generadas con entradas del gold congelado (también
`TimelineEntry`: `resumen` = la descripción anotada). Criterio: fecha dentro de
una tolerancia en días, y entre las candidatas se elige la de mayor similitud de
contenido (ROUGE-1). Emparejamiento 1-a-1 (greedy). No modifica nada aguas
arriba.

Lo consumen las métricas: Date F1 (cuenta de pares vs no-emparejados) y ROUGE
por alineamiento (sobre los pares).
"""

from __future__ import annotations

from src.schemas import TimelineEntry


def _unigramas(texto: str) -> list[str]:
    import re

    return re.findall(r"\w+", texto.lower())


def sim_rouge1(a: str, b: str) -> float:
    """F1 de solapamiento de unigramas (ROUGE-1), para ordenar candidatas."""
    ta, tb = _unigramas(a), _unigramas(b)
    if not ta or not tb:
        return 0.0
    from collections import Counter

    ca, cb = Counter(ta), Counter(tb)
    solap = sum((ca & cb).values())
    if solap == 0:
        return 0.0
    prec, rec = solap / len(ta), solap / len(tb)
    return 2 * prec * rec / (prec + rec)


def alinear(
    predicho: list[TimelineEntry],
    gold: list[TimelineEntry],
    *,
    tol_dias: int = 0,
) -> dict:
    """Empareja 1-a-1 por fecha (±tol_dias) maximizando similitud de contenido.

    Devuelve {pares, pred_sin_par, gold_sin_par}. `pares` es lista de tuplas
    (TimelineEntry predicho, TimelineEntry gold).
    """
    gold_usados: set[int] = set()
    pares: list[tuple[TimelineEntry, TimelineEntry]] = []
    pred_sin_par: list[TimelineEntry] = []

    for p in predicho:
        mejor_j, mejor_sim = -1, -1.0
        for j, g in enumerate(gold):
            if j in gold_usados:
                continue
            if abs((p.fecha - g.fecha).days) <= tol_dias:
                s = sim_rouge1(p.resumen, g.resumen)
                if s > mejor_sim:
                    mejor_sim, mejor_j = s, j
        if mejor_j >= 0:
            gold_usados.add(mejor_j)
            pares.append((p, gold[mejor_j]))
        else:
            pred_sin_par.append(p)

    gold_sin_par = [g for j, g in enumerate(gold) if j not in gold_usados]
    return {"pares": pares, "pred_sin_par": pred_sin_par, "gold_sin_par": gold_sin_par}
