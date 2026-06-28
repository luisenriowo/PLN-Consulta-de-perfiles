"""Utilidades internas compartidas por el pipeline NLP.

No importar desde fuera de src/pipeline/.
"""

from __future__ import annotations

import re
import unicodedata


def _norm(texto: str) -> str:
    """Normaliza texto para comparaciones: minúsculas, sin acentos, espacios simples."""
    sin_acentos = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_acentos.lower()).strip(" .,;:«»\"'()")
