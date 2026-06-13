"""Backbone — Normalización temporal (FIJO, compartido).

HeidelTime (español) → expresiones TIMEX3, ancladas a la fecha de publicación
(DCT) de cada documento. Requiere Java + TreeTagger (ver README / Docker).
Sin lógica todavía: stub.
"""

from __future__ import annotations

from src.schemas import Documento


def normalize_temporal(docs: list[Documento]) -> list[Documento]:
    """Resuelve expresiones temporales a fechas absolutas (TIMEX3)."""
    raise NotImplementedError
