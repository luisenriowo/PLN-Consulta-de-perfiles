"""Condición B1 — Extractivo ( §6).

Resumen extractivo clásico: selecciona la oración central del cluster. Fiel,
sin generación abstractiva. Stub.
"""

from __future__ import annotations

from src.schemas import EventCluster, TimelineEntry


class B1Extractive:
    name = "b1_extractive"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        raise NotImplementedError
