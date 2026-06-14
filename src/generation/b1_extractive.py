"""Condición B1 — Extractivo (CLAUDE.md §6).

Resumen extractivo clásico: entre las oraciones de evidencia del cluster, elige
la más CENTRAL (la más cercana al centroide de embeddings). Fiel (texto
copiado), sin generación abstractiva ni LLM. Difiere de B0 en que B0 toma
siempre el titular del primer reporte; B1 toma la oración más representativa del
conjunto.
"""

from __future__ import annotations

import numpy as np

from src.pipeline import embeddings
from src.pipeline.preprocess import segmentar_oraciones
from src.schemas import EventCluster, TimelineEntry


class B1Extractive:
    name = "b1_extractive"

    def generate(self, clusters: list[EventCluster]) -> list[TimelineEntry]:
        modelo = embeddings.modelo()
        salida: list[TimelineEntry] = []
        for c in clusters:
            oraciones: list[str] = []
            for p in c.pasajes_evidencia:
                oraciones.extend(segmentar_oraciones(p))
            # dedup preservando orden, descartando vacías
            oraciones = list(dict.fromkeys(o for o in oraciones if o))

            if not oraciones:
                resumen = ""
            elif len(oraciones) == 1:
                resumen = oraciones[0]
            else:
                emb = modelo.encode(oraciones, normalize_embeddings=True)
                centro = emb.mean(axis=0)
                resumen = oraciones[int(np.argmax(emb @ centro))]

            salida.append(
                TimelineEntry(
                    fecha=c.fecha_normalizada,
                    resumen=resumen,
                    fuentes=list(c.fuentes),
                    confianza=1.0,   # fiel por construcción (texto copiado)
                )
            )
        return salida
