"""Evaluación — Corrida del experimento ( §7, §8).

Ejecuta las 4 condiciones × N corridas (N≥3, §2.5) sobre los mismos clusters y
el gold congelado, agrega media ± desviación estándar y emite las tablas.
Loguea cada corrida y el costo de LLM. Stub.
"""

from __future__ import annotations


def run_experiment(n: int = 3) -> None:
    """Corre las 4 condiciones N veces y produce las tablas de métricas."""
    raise NotImplementedError


if __name__ == "__main__":
    run_experiment()
