"""Ensamblado de la línea de tiempo final.

Ordena las `TimelineEntry` cronológicamente. Las fuentes ya vienen adjuntas
desde la generación (invariante de atribución §2.6); aquí solo se garantiza el
orden y que ninguna entrada quede sin fuente. Común a todas las condiciones;
no transforma el contenido del resumen.
"""

from __future__ import annotations

from src.schemas import TimelineEntry


def assemble(entries: list[TimelineEntry]) -> list[TimelineEntry]:
    """Ordena las entradas por fecha (estable) y conserva sus fuentes."""
    return sorted(entries, key=lambda e: e.fecha)
