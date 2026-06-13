"""Ensamblado de la línea de tiempo final.

Ordena las `TimelineEntry` por fecha y adjunta sus fuentes. Es común a todas
las condiciones (post-generación) y no debe transformar contenido. Stub.
"""

from __future__ import annotations

from src.schemas import TimelineEntry


def assemble(entries: list[TimelineEntry]) -> list[TimelineEntry]:
    """Ordena cronológicamente y adjunta fuentes a las entradas."""
    raise NotImplementedError
