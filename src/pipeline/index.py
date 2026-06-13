"""Backbone — Índice vectorial para recuperación / RAG (FIJO, compartido).

Construye el vector store (FAISS o Chroma) sobre los pasajes de evidencia, que
el Sistema (sistema_rag) consulta para anclar la generación. Embeddings con
sentence-transformers multilingüe. Sin lógica todavía: stub.
"""

from __future__ import annotations

from src.schemas import EventCluster


def build_index(clusters: list[EventCluster]) -> object:
    """Construye el vector store de recuperación sobre los pasajes."""
    raise NotImplementedError
