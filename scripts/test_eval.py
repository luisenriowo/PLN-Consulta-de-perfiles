"""Fixture de prueba del arnés de evaluación (verdades conocidas).

NO es un placeholder: tres entradas con respuesta esperada conocida —match
perfecto, fecha desfasada, alucinación— que verifican que CADA métrica computa
bien ANTES de que llegue el gold real (advertencia del usuario, 2026-06-14).

Separa dos cosas:
  (1) lógica de las métricas → verificada con verdades conocidas y un stub.
  (2) juez NLI de alucinación → validado en los casos claros (P1 respaldado,
      P3 alucinado). Para reportar el número titular hay que validarlo contra
      un subconjunto humano real (eval.nli.validar_juez).

Uso:  python scripts/test_eval.py
"""

from __future__ import annotations

import math
from datetime import date

from eval import metrics
from eval.align import alinear
from src.schemas import TimelineEntry

# ---- GOLD (3 entradas; resumen = la descripción anotada) ----
GOLD = [
    TimelineEntry(
        fecha=date(2022, 2, 21),
        resumen="Inició el juicio oral contra Ollanta Humala por lavado de activos.",
        fuentes=["g1"],
    ),
    TimelineEntry(
        fecha=date(2023, 4, 3),
        resumen="La Procuraduría pidió 1300 millones de soles de reparación civil al Estado.",
        fuentes=["g2"],
    ),
    TimelineEntry(
        fecha=date(2025, 4, 15),
        resumen="Se dictó sentencia de primera instancia contra Ollanta Humala.",
        fuentes=["g3"],
    ),
]

# ---- PREDICHO ----
PRED = [
    # P1: match perfecto (misma fecha, resumen idéntico al gold, respaldado).
    TimelineEntry(
        fecha=date(2022, 2, 21),
        resumen="Inició el juicio oral contra Ollanta Humala por lavado de activos.",
        fuentes=["d1"],
    ),
    # P2: fecha desfasada 10 días, contenido correcto y respaldado.
    TimelineEntry(
        fecha=date(2023, 4, 13),
        resumen="La Procuraduría solicitó una reparación civil de 1300 millones de soles.",
        fuentes=["d2"],
    ),
    # P3: ALUCINACIÓN (fecha correcta, pero el resumen contradice su fuente).
    TimelineEntry(
        fecha=date(2025, 4, 15),
        resumen="Ollanta Humala fue absuelto de todos los cargos.",
        fuentes=["d3"],
    ),
]

FUENTES_TEXTO = {
    "d1": "El juicio oral contra Ollanta Humala por presunto lavado de activos comenzó esta semana en el Poder Judicial.",
    "d2": "La Procuraduría Pública solicitó 1300 millones de soles como reparación civil a favor del Estado.",
    "d3": "El Poder Judicial dictó sentencia condenatoria de primera instancia contra Ollanta Humala.",
}


def main() -> None:
    print("== Date F1 ==")
    f0 = metrics.date_f1(PRED, GOLD, tol_dias=0)
    print(f"  tol=0:  {f0}")
    assert (f0["tp"], f0["fp"], f0["fn"]) == (2, 1, 1), f0
    assert math.isclose(f0["f1"], 2 / 3, rel_tol=1e-9), f0["f1"]
    f14 = metrics.date_f1(PRED, GOLD, tol_dias=14)
    print(f"  tol=14: {f14}")
    assert f14["tp"] == 3 and math.isclose(f14["f1"], 1.0), f14
    print("  OK: con tol=0 la fecha desfasada penaliza; con tol=14 entra.")

    print("\n== ROUGE por alineamiento ==")
    pares = alinear(PRED, GOLD, tol_dias=0)["pares"]
    assert len(pares) == 2, pares
    par_p1 = next(p for p in pares if p[0] is PRED[0])
    assert math.isclose(metrics.rouge_1(par_p1[0].resumen, par_p1[1].resumen), 1.0), (
        "P1 idéntico"
    )
    r = metrics.rouge_vs_gold(PRED, GOLD, tol_dias=0)
    print(f"  rouge medio (pares alineados): {r}")
    print("  OK: el match perfecto da ROUGE-1 = 1.0.")

    print("\n== Tasa de alucinación: LÓGICA de la métrica (stub) ==")

    # stub determinista: marca como NO respaldada solo la alucinación (P3) →
    # tasa esperada = 1/3. Aísla la AGREGACIÓN del juez.
    def stub(resumen: str, premisa: str) -> bool:
        return "absuelto" not in resumen.lower()

    al = metrics.tasa_alucinacion(PRED, FUENTES_TEXTO, verificador=stub)
    print(
        f"  {{'tasa': {al['tasa']:.3f}, 'no_respaldadas': {al['no_respaldadas']}, 'total': {al['total']}}}"
    )
    assert al["no_respaldadas"] == 1 and math.isclose(
        al["tasa"], 1 / 3, rel_tol=1e-9
    ), al
    print("  OK: la agregación (fracción no respaldada) computa bien.")

    print("\n== Tasa de alucinación: JUEZ NLI en los casos claros ==")
    al_nli = metrics.tasa_alucinacion(
        PRED, FUENTES_TEXTO
    )  # verificador NLI por defecto
    veredictos = {e.fuentes[0]: ok for e, ok in al_nli["detalle"]}
    print(f"  veredictos NLI (respaldado?): {veredictos}")
    print(
        f"  tasa NLI: {al_nli['tasa']:.3f}  no_respaldadas={al_nli['no_respaldadas']}"
    )
    assert veredictos["d1"] is True, "el match perfecto debe quedar RESPALDADO"
    assert veredictos["d3"] is False, (
        "la alucinación (absuelto vs condena) debe quedar NO respaldada"
    )
    print("  OK: el juez NLI clasifica bien P1 (respaldado) y P3 (alucinado).")
    print(
        "  ⚠ Para el número titular: validar el juez con eval.nli.validar_juez "
        "sobre un subconjunto humano real (≈ las 216 entradas)."
    )

    print("\n✅ TODOS LOS CHECKS DEL ARNÉS PASARON")


if __name__ == "__main__":
    main()
