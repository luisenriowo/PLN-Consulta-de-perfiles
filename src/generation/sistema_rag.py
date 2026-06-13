"""Condición Sistema — Generación abstractiva anclada / RAG ( §6).

El LLM GENERA la descripción del evento anclada a `pasajes_evidencia` (RAG),
con cita de fuente. Descarta todo evento sin pasaje fuente que lo respalde
(invariante de atribución §2.6). Fija temperature y seed. Stub.
"""

from __future__ import annotations

from src.schemas import EventCluster, TimelineEntry


class SistemaRAG:
    name = "sistema_rag"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        raise NotImplementedError
