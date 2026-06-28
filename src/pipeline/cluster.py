"""Backbone — Clustering de eventos (FIJO, compartido por las 4 condiciones).

Agrupa documentos que hablan del MISMO evento mediante similitud semántica
(embeddings multilingües), y produce `EventCluster`. Es semántico —no léxico—
porque el corpus es casi mono-fuente (Andina republica poco): la redundancia de
evento está en el significado, no en n-gramas compartidos.

⚠ `fecha_normalizada` se ancla por ahora a la fecha de PUBLICACIÓN más temprana
del cluster (primer reporte), no a la fecha del evento resuelta por HeidelTime.
`pipeline/temporal.py` la refinará cuando esté disponible (TIMEX3). Para prensa
de agencia, pub ≈ evento, así que es una primera aproximación razonable.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from src.pipeline import embeddings
from src.schemas import Documento, EventCluster

MODELO_EMB = embeddings.MODELO_EMB
UMBRAL_DEFECTO = 0.35  # distancia coseno; menor = clusters más estrictos


def _texto_evento(doc: Documento) -> str:
    """Parte más saliente del evento: título + lead (primeras 2 líneas)."""
    return " ".join(doc.texto.split("\n")[:2]).strip() or doc.texto[:200]


def cluster_events(
    docs: list[Documento], *, umbral: float = UMBRAL_DEFECTO, modelo: str = MODELO_EMB
) -> list[EventCluster]:
    """Agrupa documentos correferentes en `EventCluster`, ordenados por fecha.

    Un documento solo (evento reportado una vez) forma su propio cluster: es un
    evento válido aunque sea de una sola nota.
    """
    if not docs:
        return []

    emb = embeddings.modelo(modelo).encode(
        [_texto_evento(d) for d in docs], normalize_embeddings=True
    )
    if len(docs) == 1:
        etiquetas = np.array([0])
    else:
        etiquetas = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=umbral,
            metric="cosine",
            linkage="average",
        ).fit_predict(emb)

    grupos: dict[int, list[Documento]] = {}
    for doc, lab in zip(docs, etiquetas):
        grupos.setdefault(int(lab), []).append(doc)

    clusters: list[EventCluster] = []
    for miembros in grupos.values():
        miembros.sort(key=lambda d: d.fecha_pub)
        # pasajes de evidencia: títulos únicos de los miembros (lo más salient)
        pasajes, vistos = [], set()
        for d in miembros:
            t = _texto_evento(d)
            if t not in vistos:
                vistos.add(t)
                pasajes.append(t)
        clusters.append(
            EventCluster(
                cluster_id="",  # se asigna tras ordenar
                fecha_normalizada=miembros[0].fecha_pub,  # primer reporte
                pasajes_evidencia=pasajes,
                fuentes=[d.doc_id for d in miembros],
                fechas_evidencia=[d.fecha_pub for d in miembros],
            )
        )

    clusters.sort(key=lambda c: c.fecha_normalizada)
    for i, c in enumerate(clusters):
        c.cluster_id = f"ev:{i:03d}"
    return clusters
