"""Condición Ablación — Generación abstractiva SIN anclaje (CLAUDE.md §6).

Misma interfaz y mismos clusters que el Sistema, pero IGNORA
`pasajes_evidencia`: el LLM genera solo a partir del sujeto y la fecha, desde su
memoria paramétrica. Aísla el efecto del grounding (RAG) sobre la tasa de
alucinación — se espera más alucinación aquí que en el Sistema.

Las `fuentes` del cluster se adjuntan igual (para una comparación justa de
atribución): el punto es que el `resumen` NO está anclado en ellas, y eso es
justo lo que mide la métrica de alucinación.
"""

from __future__ import annotations

from src.generation import _llm
from src.schemas import EventCluster, TimelineEntry

# El sistema es genérico; para este experimento el sujeto es fijo (Humala).
SUJETO = "Ollanta Humala"

_SYSTEM = (
    "Redactas entradas de una línea de tiempo de una figura política, en español.\n"
    "Resume en 1–2 oraciones qué le ocurrió a la figura indicada alrededor de la "
    "fecha dada. Tono neutral. Devuelve solo el resumen, sin preámbulo ni comillas."
)


class Ablacion:
    name = "ablacion"

    def __init__(self, sujeto: str = SUJETO) -> None:
        self.sujeto = sujeto

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        salida: list[TimelineEntry] = []
        for c in clusters:
            user = f"Figura: {self.sujeto}. Fecha: {c.fecha_normalizada.isoformat()}."
            try:
                resumen = _llm.completar(_SYSTEM, user)
            except Exception:
                continue  # cuota agotada u otro error → descarta
            salida.append(
                TimelineEntry(
                    fecha=c.fecha_normalizada,
                    resumen=resumen,
                    fuentes=list(c.fuentes),  # mismas fuentes, resumen NO anclado
                    confianza=None,
                    cluster_id=c.cluster_id,
                )
            )
        return salida
