"""Tipado inducido de relaciones abiertas.

Agrupa aristas OpenIE por similitud semántica de su `predicado` para que una
persona nombre cada cluster con un tipo interpretable. El mapeo resultante se
persiste en `RelationEdge.tipo` sin cambiar el contrato del grafo.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from src.pipeline import embeddings
from src.pipeline._utils import _norm
from src.storage import KnowledgeGraph


@dataclass(frozen=True)
class PredicateInstance:
    """Una arista abierta lista para tipado inducido."""

    relation_id: int
    predicado: str
    origen_id: str
    destino_id: str
    origen_nombre: str
    destino_nombre: str
    fecha: object
    evidencia: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationTypeCluster:
    """Cluster inducido de predicados relacionales."""

    cluster_id: str
    instances: list[PredicateInstance]

    @property
    def n(self) -> int:
        return len(self.instances)

    @property
    def predicados_top(self) -> list[tuple[str, int]]:
        return Counter(i.predicado for i in self.instances).most_common(8)

    @property
    def ejemplos(self) -> list[str]:
        vistos: set[str] = set()
        ejemplos: list[str] = []
        for inst in self.instances:
            texto = (
                inst.evidencia[0]
                if inst.evidencia
                else (
                    f"{inst.origen_nombre} --{inst.predicado}-- {inst.destino_nombre}"
                )
            )
            if texto not in vistos:
                vistos.add(texto)
                ejemplos.append(texto)
            if len(ejemplos) >= 3:
                break
        return ejemplos


def cargar_predicados(grafo: KnowledgeGraph) -> list[PredicateInstance]:
    """Lee aristas abiertas del grafo, ordenadas para clustering reproducible."""
    instancias: list[PredicateInstance] = []
    for row in sorted(grafo.relations(), key=lambda r: int(r["id"])):
        predicado = (row.get("predicado") or "").strip()
        if not predicado:
            continue
        # Descartar artefactos de OpenIE: URLs y fragmentos largos no son predicados
        # (p. ej. enlaces "https://andina.pe/...galeer" que el parser tomó por verbo).
        if len(predicado) > 40 or "http" in predicado or "://" in predicado:
            continue
        evidencia = grafo.evidencia(int(row["id"])).get("pasajes", [])
        instancias.append(
            PredicateInstance(
                relation_id=int(row["id"]),
                predicado=predicado,
                origen_id=row["origen_id"],
                destino_id=row["destino_id"],
                origen_nombre=row.get("origen_nombre") or row["origen_id"],
                destino_nombre=row.get("destino_nombre") or row["destino_id"],
                fecha=row["fecha"],
                evidencia=evidencia,
            )
        )
    return instancias


def texto_embedding(inst: PredicateInstance) -> str:
    """Texto corto y anónimo para embeddear la relación, no el tema noticioso."""
    return f"ENT_A {_norm(inst.predicado)} ENT_B"


def clusterizar_predicados(
    instancias: list[PredicateInstance],
    *,
    distance_threshold: float = 0.35,
    modelo: str = embeddings.MODELO_EMB,
    vectores: np.ndarray | None = None,
) -> list[RelationTypeCluster]:
    """Agrupa predicados con clustering jerárquico coseno.

    `vectores` permite tests offline deterministas sin cargar SentenceTransformer.
    """
    if not instancias:
        return []
    # Clusterizar PREDICADOS ÚNICOS, no aristas. A escala hay decenas de miles de
    # aristas pero solo unos miles de predicados distintos; embeber/clusterizar por
    # arista es O(n_aristas²) y agota memoria (93k aristas → matriz inviable).
    # `vectores` (tests offline) se alinea al orden de `predicados` (sorted).
    by_pred: dict[str, list[PredicateInstance]] = {}
    for inst in instancias:
        by_pred.setdefault(_norm(inst.predicado), []).append(inst)
    predicados = sorted(by_pred)

    if vectores is None:
        vectores = embeddings.modelo(modelo).encode(
            [f"ENT_A {p} ENT_B" for p in predicados], normalize_embeddings=True, show_progress_bar=True
        )
    vectores = np.asarray(vectores)

    if len(predicados) == 1:
        labels = np.array([0])
    else:
        labels = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=distance_threshold,
        ).fit_predict(vectores)

    grupos: dict[int, list[PredicateInstance]] = {}
    for pred, label in zip(predicados, labels):
        grupos.setdefault(int(label), []).extend(by_pred[pred])

    ordenados = sorted(
        grupos.values(),
        key=lambda xs: (
            -len(xs),
            Counter(i.predicado for i in xs).most_common(1)[0][0],
            min(i.relation_id for i in xs),
        ),
    )
    return [
        RelationTypeCluster(cluster_id=f"reltype:{i:03d}", instances=grupo)
        for i, grupo in enumerate(ordenados)
    ]


def asignaciones(clusters: list[RelationTypeCluster]) -> list[dict]:
    """Filas arista→cluster para persistencia y evaluación."""
    filas: list[dict] = []
    for cluster in clusters:
        for inst in cluster.instances:
            filas.append(
                {
                    "relation_id": inst.relation_id,
                    "cluster_id": cluster.cluster_id,
                    "predicado": inst.predicado,
                    "origen": inst.origen_nombre,
                    "destino": inst.destino_nombre,
                    "fecha": inst.fecha,
                }
            )
    return sorted(filas, key=lambda r: int(r["relation_id"]))


def etiquetas_desde_csv(path: str | Path) -> dict[str, str]:
    """Lee `cluster_id,tipo_label` desde el CSV anotado por humanos."""
    etiquetas: dict[str, str] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cluster_id = (row.get("cluster_id") or "").strip()
            tipo = (row.get("tipo_label") or "").strip()
            if cluster_id and tipo:
                etiquetas[cluster_id] = tipo
    return etiquetas


def aplicar_etiquetas(
    grafo: KnowledgeGraph,
    rows: list[dict],
    etiquetas: dict[str, str],
) -> int:
    """Persiste `tipo` en `relations` usando asignaciones y etiquetas humanas."""
    n = 0
    for row in rows:
        tipo = etiquetas.get(row["cluster_id"])
        if not tipo:
            continue
        grafo.update_relation_type(int(row["relation_id"]), tipo)
        n += 1
    return n
