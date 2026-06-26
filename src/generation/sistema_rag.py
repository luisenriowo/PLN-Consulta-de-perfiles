"""Condición Sistema — Generación abstractiva anclada / RAG (CLAUDE.md §6).

El LLM GENERA la descripción del evento anclada EXCLUSIVAMENTE a
`pasajes_evidencia` (RAG), en español, neutral y atribuida (caso disputado).
Si los pasajes no respaldan un evento concreto, el modelo responde SIN_RESPALDO
y la entrada se DESCARTA (invariante de atribución §2.6).

No necesita un vector store aparte: el clustering ya agrupó los documentos del
evento, así que sus `pasajes_evidencia` SON el contexto de anclaje. Por eso
`pipeline/index.py` queda como stub para este diseño cluster-nivel.
"""

from __future__ import annotations

from src.generation import _llm
from src.schemas import EventCluster, TimelineEntry

_SIN_RESPALDO = "SIN_RESPALDO"

_SYSTEM = (
    "Redactas entradas de una línea de tiempo de una figura política, en español.\n"
    "REGLAS ESTRICTAS:\n"
    "- Resume el evento en 1–2 oraciones usando SOLO información presente en los "
    "PASAJES. No agregues hechos, fechas, cifras ni nombres que no estén ahí.\n"
    "- Es un caso legal DISPUTADO: atribuye lo contestado ('según la fiscalía', "
    "'el expresidente niega…') y describe el hecho procesal; NO afirmes culpabilidad.\n"
    "- Tono neutral, sin adjetivos valorativos ni framing.\n"
    f"- Si los pasajes no permiten describir un evento concreto, responde exactamente {_SIN_RESPALDO}.\n"
    "Devuelve solo el resumen, sin preámbulo ni comillas."
)


class SistemaRAG:
    name = "sistema_rag"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        salida: list[TimelineEntry] = []
        for c in clusters:
            pasajes = "\n".join(f"- {p}" for p in c.pasajes_evidencia)
            try:
                resumen = _llm.completar(_SYSTEM, f"PASAJES:\n{pasajes}")
            except Exception:
                continue   # cuota agotada u otro error → descarta
            if not resumen or _SIN_RESPALDO in resumen:
                continue   # descarta lo no respaldado (§2.6)
            salida.append(
                TimelineEntry(
                    fecha=c.fecha_normalizada,
                    resumen=resumen,
                    fuentes=list(c.fuentes),
                    confianza=None,
                    cluster_id=c.cluster_id,
                )
            )
        return salida
