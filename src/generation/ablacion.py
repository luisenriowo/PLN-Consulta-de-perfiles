"""Condición Ablación — Generación abstractiva SIN anclaje ( §6).

El LLM genera SIN los pasajes de evidencia / sin la restricción de anclaje.
Aísla el efecto del grounding (RAG) sobre la tasa de alucinación. Misma
interfaz, mismos clusters de entrada, pero ignora `pasajes_evidencia`. Stub.
"""

from __future__ import annotations

from src.schemas import EventCluster, TimelineEntry


class Ablacion:
    name = "ablacion"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        raise NotImplementedError
