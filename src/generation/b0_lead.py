"""Condición B0 — Lead ( §6).

Copia el titular / oración líder del cluster. Fiel por construcción, baja
calidad: es el piso de la comparación. Sin generación real. Stub.
"""

from __future__ import annotations

from src.schemas import EventCluster, TimelineEntry


class B0Lead:
    name = "b0_lead"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        raise NotImplementedError
