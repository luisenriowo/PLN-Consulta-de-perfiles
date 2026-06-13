"""Backbone — Selección de saliencia (FIJO, compartido).

Filtra los `EventCluster` para quedarse con los eventos salientes que entran a
la línea de tiempo. Esta es la última etapa del backbone antes del punto de
swap: su salida es idéntica para las 4 condiciones. Sin lógica todavía: stub.
"""

from __future__ import annotations

from src.schemas import EventCluster


def select_salient(clusters: list[EventCluster]) -> list[EventCluster]:
    """Selecciona los clusters de evento salientes."""
    raise NotImplementedError
