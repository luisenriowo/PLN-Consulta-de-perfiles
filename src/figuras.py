"""Configuración por figura (desambiguación + queries + ventana).

Cada figura necesita su config de desambiguación o el timeline sale contaminado
con homónimos: para Humala, excluir Antauro/Isaac/Nadine. El script de
precómputo (`scripts/precompute_figura.py`) recibe esta config por figura.

Solo lo importa el precómputo (no la API), así que puede arrastrar el backbone.

Para AÑADIR una figura nueva:
  1. Agrega un `FiguraConfig` a `FIGURAS` con:
       - `gazetteer`: superficie normalizada (minúsculas, sin acentos) ->
         (id_canónico, nombre). Incluye al sujeto y a sus homónimos.
       - `sujeto_id`: el id canónico del sujeto.
       - `familia_otros`: ids de homónimos a EXCLUIR del protagonismo.
       - `queries`: términos de búsqueda en Andina (términos sueltos, no frases).
       - `desde`/`hasta`: ventana temporal alcanzable.
  2. Corre `python scripts/precompute_figura.py <slug>`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.ingest._util import FECHA_CORTE_HUMALA, FECHA_INICIO_HUMALA
# Fuente única del gazetteer/familia de Humala (definidos en el backbone):
from src.pipeline.entities import _GAZETTEER as _GZ_HUMALA
from src.pipeline.protagonism import _FAMILIA_OTROS as _FAM_HUMALA


@dataclass(frozen=True)
class FiguraConfig:
    slug: str
    nombre: str
    sujeto_id: str
    queries: tuple[str, ...]
    gazetteer: dict[str, tuple[str, str]]
    familia_otros: frozenset[str]
    desde: date = FECHA_INICIO_HUMALA
    hasta: date = FECHA_CORTE_HUMALA


FIGURAS: dict[str, FiguraConfig] = {
    "humala": FiguraConfig(
        slug="humala",
        nombre="Ollanta Humala",
        sujeto_id="humala:ollanta",
        queries=(
            "Ollanta Humala", "Odebrecht", "Gasoducto Sur", "Madre Mía",
            "Lava Jato", "Nadine Heredia",
        ),
        gazetteer=_GZ_HUMALA,
        familia_otros=frozenset(_FAM_HUMALA),
    ),
    # Keiko: excluir a Alberto (padre) y Kenji (hermano) — "Fujimori" a secas es
    # ambiguo, así que NO se enlaza solo el apellido; el protagonismo se apoya en
    # "Keiko"/"Keiko Fujimori" en título/lead.
    "keiko": FiguraConfig(
        slug="keiko",
        nombre="Keiko Fujimori",
        sujeto_id="fujimori:keiko",
        queries=(
            "Keiko Fujimori", "Fuerza Popular", "Cócteles", "Lava Jato", "Fujimori",
        ),
        gazetteer={
            "keiko fujimori": ("fujimori:keiko", "Keiko Fujimori"),
            "keiko sofia fujimori higuchi": ("fujimori:keiko", "Keiko Fujimori"),
            "keiko": ("fujimori:keiko", "Keiko Fujimori"),
            "alberto fujimori": ("fujimori:alberto", "Alberto Fujimori"),
            "kenji fujimori": ("fujimori:kenji", "Kenji Fujimori"),
            "kenji": ("fujimori:kenji", "Kenji Fujimori"),
            "fuerza popular": ("org:fuerza-popular", "Fuerza Popular"),
        },
        familia_otros=frozenset({"fujimori:alberto", "fujimori:kenji"}),
    ),
}


def cargar(slug: str) -> FiguraConfig:
    if slug not in FIGURAS:
        raise KeyError(
            f"No hay config para '{slug}'. Figuras disponibles: {sorted(FIGURAS)}. "
            "Añade un FiguraConfig en src/figuras.py."
        )
    return FIGURAS[slug]
