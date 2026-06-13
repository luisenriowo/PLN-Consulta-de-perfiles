"""Evaluación — Métricas ( §7).

- Date F1: selección de fechas correctas vs gold.
- ROUGE por alineamiento: calidad de contenido vs gold.
- Tasa de alucinación (métrica estrella): proporción de entradas cuyo resumen
  no está respaldado por sus fuentes (muestra manual o NLI/entailment en es).

Todo se reporta como media ± desviación estándar sobre N corridas. Stub.
"""

from __future__ import annotations

from src.schemas import TimelineEntry


def date_f1(predicho: list[TimelineEntry], gold: list[TimelineEntry]) -> float:
    """F1 sobre las fechas seleccionadas frente al gold."""
    raise NotImplementedError


def rouge_alineado(alineamientos: list[tuple]) -> dict:
    """ROUGE calculado sobre los pares alineados predicho↔gold."""
    raise NotImplementedError


def tasa_alucinacion(entries: list[TimelineEntry]) -> float:
    """Proporción de entradas no respaldadas por sus fuentes."""
    raise NotImplementedError
