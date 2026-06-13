"""Evaluación — Alineamiento predicho ↔ gold ( §4 eval/).

Alinea las `TimelineEntry` generadas con las entradas del gold congelado por
fecha + contenido. No modifica nada aguas arriba. Stub.
"""

from __future__ import annotations

from src.schemas import TimelineEntry


def align(predicho: list[TimelineEntry], gold: list[TimelineEntry]) -> list[tuple]:
    """Empareja entradas predichas con entradas gold (fecha + contenido)."""
    raise NotImplementedError
