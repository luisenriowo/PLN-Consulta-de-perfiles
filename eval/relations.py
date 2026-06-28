"""Evaluación — Clasificador de relaciones (Fase 1: confianza en las relaciones).

Mide la calidad del `RelationClassifier` contra un gold humano: precisión,
recall y F1 POR TIPO de relación, accuracy, macro-F1 y matriz de confusión.
Permite comparar los tres clasificadores (reglas, híbrido, LLM) sobre los MISMOS
ejemplos — la base para decidir el umbral híbrido (Fase 1.3) con número en mano.

Es la métrica estrella del pivote tema-céntrico: reemplaza a la tasa de
alucinación de generación como criterio de calidad del sistema.

Formato del gold (CSV, una fila por co-ocurrencia etiquetada). Columnas:
  entity_a, entity_b, oracion, doc_id, fecha,
  triple_sujeto, triple_verbo, triple_objeto,  # opcionales: reproducen el path
                                               #   de reglas (verbo del dep-triple)
  tipo_sugerido,                               # sugerencia automática (NO se usa)
  tipo_gold                                     # etiqueta humana (clave de TIPOS_RELACION)

Las filas con `tipo_gold` vacío se omiten (aún sin etiquetar). El arnés se valida
con verdades conocidas (scripts/test_relations.py) ANTES del gold real, igual que
el arnés de generación (scripts/test_eval.py).

Uso:  python -m eval.relations annotation/gold_relaciones/<slug>.csv [--llm]
"""

from __future__ import annotations

import csv
from datetime import date

from src.pipeline.relation_classifier import (
    HybridClassifier,
    LLMClassifier,
    RuleBasedClassifier,
)
from src.pipeline.relations import Coocurrencia
from src.schemas import TIPOS_RELACION, EntityNode

TIPOS = list(TIPOS_RELACION)


def _entidad(nombre: str) -> EntityNode:
    """EntityNode mínimo: los clasificadores solo usan `nombre` (no tipo/id)."""
    return EntityNode(entity_id=nombre, nombre=nombre, tipo="PER")


def fila_a_ejemplo(row: dict) -> tuple[Coocurrencia, str] | None:
    """Convierte una fila del gold en (Coocurrencia, tipo_gold).

    Devuelve None si la fila no está etiquetada (`tipo_gold` vacío). Lanza
    ValueError si el tipo_gold no pertenece a la taxonomía.
    """
    tipo_gold = (row.get("tipo_gold") or "").strip()
    if not tipo_gold:
        return None
    if tipo_gold not in TIPOS_RELACION:
        raise ValueError(f"tipo_gold inválido {tipo_gold!r}. Válidos: {TIPOS}")
    verbo = (row.get("triple_verbo") or "").strip()
    triple = (
        (row.get("triple_sujeto", ""), verbo, row.get("triple_objeto", ""))
        if verbo
        else None
    )
    try:
        fecha = date.fromisoformat((row.get("fecha") or "").strip())
    except ValueError:
        fecha = date(2021, 1, 1)
    cooc = Coocurrencia(
        entity_a=_entidad(row["entity_a"]),
        entity_b=_entidad(row["entity_b"]),
        oracion=row["oracion"],
        doc_id=row.get("doc_id", ""),
        fecha=fecha,
        triple=triple,
    )
    return cooc, tipo_gold


def cargar_gold(path) -> list[tuple[Coocurrencia, str]]:
    """Lee el CSV de gold y devuelve los ejemplos etiquetados."""
    with open(path, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    ejemplos = [e for e in (fila_a_ejemplo(r) for r in filas) if e is not None]
    if not ejemplos:
        raise ValueError(
            f"{path}: 0 filas etiquetadas (la columna 'tipo_gold' está vacía)."
        )
    return ejemplos


def evaluar(clasificador, ejemplos: list[tuple[Coocurrencia, str]]) -> dict:
    """Predice cada ejemplo y computa P/R/F1 por tipo + matriz de confusión.

    Devuelve: por_tipo {tipo: {precision, recall, f1, support}}, accuracy,
    macro_f1 (media de F1 sobre tipos con soporte), confusion {(gold, pred): n},
    metodos {metodo: n} (trazabilidad: cuántas predicciones vinieron de reglas/
    llm/hybrid) y n.
    """
    confusion: dict[tuple[str, str], int] = {}
    metodos: dict[str, int] = {}
    correctos = 0
    for cooc, gold in ejemplos:
        res = clasificador.classify(cooc)
        pred = res.tipo
        confusion[(gold, pred)] = confusion.get((gold, pred), 0) + 1
        metodos[res.metodo] = metodos.get(res.metodo, 0) + 1
        if pred == gold:
            correctos += 1
    n = len(ejemplos)

    por_tipo: dict[str, dict] = {}
    for t in TIPOS:
        tp = confusion.get((t, t), 0)
        fp = sum(v for (g, p), v in confusion.items() if p == t and g != t)
        fn = sum(v for (g, p), v in confusion.items() if g == t and p != t)
        support = sum(v for (g, _p), v in confusion.items() if g == t)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        por_tipo[t] = {"precision": prec, "recall": rec, "f1": f1, "support": support}

    con_soporte = [t for t in TIPOS if por_tipo[t]["support"] > 0]
    macro_f1 = (
        sum(por_tipo[t]["f1"] for t in con_soporte) / len(con_soporte)
        if con_soporte
        else 0.0
    )
    return {
        "por_tipo": por_tipo,
        "accuracy": correctos / n if n else 0.0,
        "macro_f1": macro_f1,
        "confusion": confusion,
        "metodos": metodos,
        "n": n,
    }


def formato(nombre: str, m: dict) -> str:
    """Tabla legible de un resultado de `evaluar`."""
    out = [
        f"== {nombre} ==  n={m['n']}  accuracy={m['accuracy']:.3f}  "
        f"macro-F1={m['macro_f1']:.3f}  métodos={m['metodos']}",
        f"  {'tipo':14s} {'P':>6s} {'R':>6s} {'F1':>6s} {'sup':>5s}",
    ]
    for t in TIPOS:
        d = m["por_tipo"][t]
        if d["support"] == 0:
            continue
        out.append(
            f"  {t:14s} {d['precision']:6.2f} {d['recall']:6.2f} "
            f"{d['f1']:6.2f} {d['support']:5d}"
        )
    return "\n".join(out)


def comparar(
    ejemplos: list[tuple[Coocurrencia, str]], *, con_llm: bool = False
) -> dict[str, dict]:
    """Evalúa los clasificadores disponibles sobre los mismos ejemplos.

    Sin `con_llm` solo evalúa REGLAS (baseline offline, sin API key). Con
    `con_llm` agrega el híbrido (umbral por defecto, puede escalar al LLM) y el
    LLM puro — la comparación que decide el umbral (Fase 1.3).
    """
    res = {"reglas": evaluar(RuleBasedClassifier(), ejemplos)}
    if con_llm:
        res["hibrido"] = evaluar(HybridClassifier(), ejemplos)
        res["llm"] = evaluar(LLMClassifier(), ejemplos)
    return res


def main(argv: list[str] | None = None) -> None:
    import sys

    argv = argv if argv is not None else sys.argv[1:]
    con_llm = "--llm" in argv
    rutas = [a for a in argv if not a.startswith("--")]
    if not rutas:
        print("Uso: python -m eval.relations <gold.csv> [--llm]")
        raise SystemExit(1)

    ejemplos = cargar_gold(rutas[0])
    print(f"Gold: {len(ejemplos)} ejemplos etiquetados ({rutas[0]})\n")
    for nombre, m in comparar(ejemplos, con_llm=con_llm).items():
        print(formato(nombre, m))
        print()


if __name__ == "__main__":
    main()
