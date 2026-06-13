"""Contrato del punto de swap ( §2.2, §5).

TODAS las condiciones (B0, B1, Sistema, Ablación) implementan esta misma
interfaz: misma entrada (`list[EventCluster]`), misma forma de salida
(`list[TimelineEntry]`). Si una condición filtra o transforma distinto aguas
arriba de aquí, la comparación queda contaminada.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.schemas import EventCluster, TimelineEntry


@runtime_checkable
class GenerationCondition(Protocol):
    """Interfaz que implementa cada condición de generación."""

    name: str

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        """Convierte clusters de evento en entradas de línea de tiempo."""
        ...
