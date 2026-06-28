"""Condición B0 — Lead (CLAUDE.md §6).

Copia la oración líder (titular) del documento representativo del cluster. Fiel
por construcción, baja calidad: es el PISO de la comparación. Sin generación
real, sin LLM. La fecha y las fuentes salen del cluster.
"""

from __future__ import annotations

from src.pipeline.preprocess import segmentar_oraciones
from src.schemas import EventCluster, TimelineEntry


class B0Lead:
    name = "b0_lead"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        salida: list[TimelineEntry] = []
        for c in clusters:
            base = c.pasajes_evidencia[0] if c.pasajes_evidencia else ""
            oraciones = segmentar_oraciones(base)
            resumen = oraciones[0] if oraciones else base
            salida.append(
                TimelineEntry(
                    fecha=c.fecha_normalizada,
                    resumen=resumen,
                    fuentes=list(c.fuentes),
                    confianza=1.0,  # fiel por construcción (texto copiado)
                    cluster_id=c.cluster_id,
                )
            )
        return salida
