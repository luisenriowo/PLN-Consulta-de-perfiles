"""Evaluación de extracción abierta de relaciones.

Consume el CSV generado por `scripts/export_openie_gold.py`. Las filas sin
etiqueta humana se omiten para permitir anotación incremental.
"""

from __future__ import annotations

import csv


def _binario(valor: str) -> int | None:
    valor = (valor or "").strip().lower()
    if valor in {"1", "si", "sí", "true", "y", "yes"}:
        return 1
    if valor in {"0", "no", "false", "n"}:
        return 0
    return None


def evaluar(path: str) -> dict:
    """Devuelve precisión de triple y predicado sobre filas anotadas."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    triples = [_binario(r.get("triple_valido_gold", "")) for r in rows]
    preds = [_binario(r.get("predicado_ok_gold", "")) for r in rows]
    triples = [x for x in triples if x is not None]
    preds = [x for x in preds if x is not None]
    return {
        "n_triple": len(triples),
        "precision_triple": sum(triples) / len(triples) if triples else 0.0,
        "n_predicado": len(preds),
        "precision_predicado": sum(preds) / len(preds) if preds else 0.0,
    }


def formato(m: dict) -> str:
    return (
        "== OpenIE ==\n"
        f"  triple válido:   n={m['n_triple']}  precision={m['precision_triple']:.3f}\n"
        f"  predicado OK:    n={m['n_predicado']}  precision={m['precision_predicado']:.3f}"
    )


def main(argv: list[str] | None = None) -> None:
    import sys

    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(
            "Uso: python -m eval.openie annotation/gold_relaciones_abiertas/<slug>.csv"
        )
        raise SystemExit(1)
    print(formato(evaluar(argv[0])))


if __name__ == "__main__":
    main()
