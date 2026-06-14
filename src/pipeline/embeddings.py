"""Embeddings compartidos (modelo multilingüe cacheado).

Un único punto de carga del SentenceTransformer para que clustering (backbone)
y B1 (extractivo) compartan el mismo modelo en memoria. CLAUDE.md §4.
"""

from __future__ import annotations

import functools

from sentence_transformers import SentenceTransformer

MODELO_EMB = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@functools.lru_cache(maxsize=1)
def modelo(nombre: str = MODELO_EMB) -> SentenceTransformer:
    return SentenceTransformer(nombre)
