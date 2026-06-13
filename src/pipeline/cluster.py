"""Backbone — Clustering de eventos (FIJO, compartido).

Genera candidatos de evento y los agrupa por correferencia entre documentos
en `EventCluster`. Sin lógica todavía: stub.
"""

from __future__ import annotations

from src.schemas import Documento, EventCluster


def cluster_events(docs: list[Documento]) -> list[EventCluster]:
    """Agrupa menciones de evento correferentes en clusters."""
    raise NotImplementedError
