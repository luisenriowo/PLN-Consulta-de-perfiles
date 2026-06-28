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
  2. Corre `uv run python scripts/precompute_figura.py <slug>`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.ingest._util import FECHA_CORTE_HUMALA, FECHA_INICIO_HUMALA
# Fuente única del gazetteer/familia de Humala (definidos en el backbone):
from src.pipeline.entities import _GAZETTEER as _GZ_HUMALA
from src.pipeline.entities import _norm
from src.pipeline.protagonism import _FAMILIA_OTROS as _FAM_HUMALA

# Figuras creadas desde la web se persisten aquí (gitignored, en data/).
_DINAMICAS = Path("data/figuras_dinamicas.json")


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


@dataclass(frozen=True)
class TemaConfig:
    """Configuración de un TEMA (enfoque tema-céntrico).

    A diferencia de `FiguraConfig`, un tema NO tiene sujeto único ni gazetteer de
    desambiguación: las entidades se descubren automáticamente del corpus
    (`entity_discovery`) y el grafo de relaciones es el producto. Solo necesita
    qué buscar, en qué ventana, cuántas entidades retener y el país (contexto
    para el lookup de Wikidata).
    """

    slug: str
    nombre: str
    queries: tuple[str, ...]
    desde: date = FECHA_INICIO_HUMALA
    hasta: date = FECHA_CORTE_HUMALA
    top_n: int = 20
    pais: str = "Perú"
    # Colectores de ingesta a usar (multi-fuente). Soportados: "andina", "gdelt".
    # GDELT aporta medios independientes (corrobora eventos → señal multi_fuente).
    fuentes: tuple[str, ...] = ("andina",)


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
    # Roberto Sánchez: apellido común. NO se enlaza "Sánchez" a secas; se exige
    # "Roberto Sánchez". Homónimo a excluir: Pedro Sánchez (presidente de España,
    # aparece en notas internacionales).
    "roberto-sanchez": FiguraConfig(
        slug="roberto-sanchez",
        nombre="Roberto Sánchez",
        sujeto_id="sanchez:roberto",
        queries=(
            "Roberto Sánchez", "Sánchez Palomino", "Juntos por el Perú", "Mincetur",
        ),
        gazetteer={
            "roberto sanchez": ("sanchez:roberto", "Roberto Sánchez"),
            "roberto sanchez palomino": ("sanchez:roberto", "Roberto Sánchez"),
            "pedro sanchez": ("sanchez:pedro", "Pedro Sánchez"),
            "juntos por el peru": ("org:juntos-peru", "Juntos por el Perú"),
        },
        familia_otros=frozenset({"sanchez:pedro"}),
    ),
}


TEMAS: dict[str, TemaConfig] = {
    "elecciones-2021-2026": TemaConfig(
        slug="elecciones-2021-2026",
        nombre="Elecciones generales 2021–2026",
        queries=(
            "elecciones generales", "segunda vuelta", "JNE", "ONPE",
            "Pedro Castillo", "Keiko Fujimori", "Perú Libre", "Fuerza Popular",
            "Dina Boluarte", "vacancia presidencial",
        ),
        top_n=20,
        fuentes=("andina", "gdelt"),   # multi-fuente: Andina + medios independientes
    ),
}


def cargar(slug: str) -> FiguraConfig:
    """Config de una figura: primero el registro en código, luego las dinámicas
    (creadas desde la web)."""
    if slug in FIGURAS:
        return FIGURAS[slug]
    dinamicas = _cargar_dinamicas()
    if slug in dinamicas:
        return dinamicas[slug]
    raise KeyError(f"No hay config para '{slug}'.")


def cargar_tema(slug: str) -> TemaConfig:
    """Config de un tema (enfoque tema-céntrico).

    Si el slug no es un tema registrado pero existe una figura/corpus con ese
    slug, lo ADAPTA a `TemaConfig` (mismo corpus, mismas queries, sin sujeto).
    Esto permite construir el grafo tema-céntrico reutilizando un corpus ya
    descargado, sin re-scrapear — útil para validar el pipeline.
    """
    if slug in TEMAS:
        return TEMAS[slug]
    try:
        fig = cargar(slug)
    except KeyError:
        raise KeyError(
            f"No hay tema ni figura con slug '{slug}'. "
            f"Temas: {sorted(TEMAS)} | Figuras: {sorted(FIGURAS)}"
        ) from None
    return TemaConfig(
        slug=fig.slug, nombre=fig.nombre, queries=fig.queries,
        desde=fig.desde, hasta=fig.hasta,
    )


def construir_config(
    slug: str, nombre: str, homonimos=(), terminos=()
) -> FiguraConfig:
    """Arma un FiguraConfig desde input de formulario.

    El gazetteer exige el NOMBRE COMPLETO para enlazar (vía contención de
    tokens), así que apellidos sueltos no enlazan (evita falsos positivos). Los
    homónimos se registran y se excluyen del protagonismo (anti-contaminación).
    """
    sid = f"fig:{slug}"
    gazetteer = {_norm(nombre): (sid, nombre)}
    familia: set[str] = set()
    for i, h in enumerate(homonimos):
        h = (h or "").strip()
        if not h:
            continue
        hid = f"{slug}:hom{i}"
        gazetteer[_norm(h)] = (hid, h)
        familia.add(hid)
    queries = tuple([nombre] + [t.strip() for t in terminos if t and t.strip()])
    return FiguraConfig(
        slug=slug, nombre=nombre, sujeto_id=sid, queries=queries,
        gazetteer=gazetteer, familia_otros=frozenset(familia),
    )


def _cfg_to_json(c: FiguraConfig) -> dict:
    return {
        "slug": c.slug, "nombre": c.nombre, "sujeto_id": c.sujeto_id,
        "queries": list(c.queries),
        "gazetteer": {k: list(v) for k, v in c.gazetteer.items()},
        "familia_otros": sorted(c.familia_otros),
        "desde": c.desde.isoformat(), "hasta": c.hasta.isoformat(),
    }


def _cfg_from_json(d: dict) -> FiguraConfig:
    return FiguraConfig(
        slug=d["slug"], nombre=d["nombre"], sujeto_id=d["sujeto_id"],
        queries=tuple(d["queries"]),
        gazetteer={k: tuple(v) for k, v in d["gazetteer"].items()},
        familia_otros=frozenset(d["familia_otros"]),
        desde=date.fromisoformat(d["desde"]), hasta=date.fromisoformat(d["hasta"]),
    )


def _cargar_dinamicas() -> dict[str, FiguraConfig]:
    if not _DINAMICAS.exists():
        return {}
    crudo = json.loads(_DINAMICAS.read_text(encoding="utf-8"))
    return {s: _cfg_from_json(d) for s, d in crudo.items()}


def guardar_dinamica(cfg: FiguraConfig) -> None:
    _DINAMICAS.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(_DINAMICAS.read_text(encoding="utf-8")) if _DINAMICAS.exists() else {}
    data[cfg.slug] = _cfg_to_json(cfg)
    _DINAMICAS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
