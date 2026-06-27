"""Storage — Grafo de conocimiento con DuckDB + NetworkX.

DuckDB  → persistencia y queries analíticas (SQL estándar, sin servidor).
          Lee los Parquet del corpus directamente sin duplicar datos.
NetworkX → análisis de grafo en memoria: centralidad, comunidades, caminos.

Un archivo por figura: data/graph_<slug>.duckdb
El schema se crea automáticamente en el primer uso (idempotente).

Uso básico:
    with KnowledgeGraph("castillo") as g:
        g.upsert_entity(node)
        g.insert_relation(edge)
        comunidades = g.comunidades()
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import networkx as nx

from src.schemas import EntityNode, RelationEdge

_DATA = Path(os.environ.get("TIMELINE_DATA_DIR", "data"))

_DDL = """
-- Secuencias para auto-increment (DuckDB no soporta AUTOINCREMENT/IDENTITY nativo).
CREATE SEQUENCE IF NOT EXISTS _seq_relations;
CREATE SEQUENCE IF NOT EXISTS _seq_evidence;
CREATE SEQUENCE IF NOT EXISTS _seq_sources;

CREATE TABLE IF NOT EXISTS entities (
    entity_id   TEXT PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    tipo        TEXT    NOT NULL,
    wikidata_id TEXT,
    n_docs      INTEGER DEFAULT 0,
    n_menciones INTEGER DEFAULT 0,
    alias       JSON    DEFAULT '[]',
    metadata    JSON    DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS relations (
    id          INTEGER PRIMARY KEY DEFAULT nextval('_seq_relations'),
    figura_slug TEXT    NOT NULL,
    origen_id   TEXT    NOT NULL REFERENCES entities(entity_id),
    destino_id  TEXT    NOT NULL REFERENCES entities(entity_id),
    tipo        TEXT    NOT NULL,
    fecha       DATE    NOT NULL,
    confianza   REAL    NOT NULL,
    metodo      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS relation_evidence (
    id          INTEGER PRIMARY KEY DEFAULT nextval('_seq_evidence'),
    relation_id INTEGER NOT NULL REFERENCES relations(id),
    pasaje      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS relation_sources (
    id          INTEGER PRIMARY KEY DEFAULT nextval('_seq_sources'),
    relation_id INTEGER NOT NULL REFERENCES relations(id),
    doc_id      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rel_slug   ON relations(figura_slug);
CREATE INDEX IF NOT EXISTS idx_rel_origen ON relations(origen_id);
CREATE INDEX IF NOT EXISTS idx_rel_dest   ON relations(destino_id);
CREATE INDEX IF NOT EXISTS idx_rel_fecha  ON relations(fecha);
CREATE INDEX IF NOT EXISTS idx_rel_tipo   ON relations(tipo);
"""


class KnowledgeGraph:
    """Interfaz de alto nivel sobre DuckDB + NetworkX para una figura.

    read_only=True abre la BD sin write-lock (varios lectores concurrentes,
    sin crear el archivo si no existe). Úsalo en la API FastAPI.
    Soporta uso como context manager (`with KnowledgeGraph(slug) as g:`).
    """

    def __init__(self, slug: str, *, read_only: bool = False) -> None:
        self.slug = slug
        import duckdb
        if not read_only:
            _DATA.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(
            str(_DATA / f"graph_{slug}.duckdb"), read_only=read_only
        )
        if not read_only:
            self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(_DDL)

    # ── Escritura ──────────────────────────────────────────────────────────

    def upsert_entity(self, node: EntityNode) -> None:
        """Inserta o actualiza una entidad (upsert por entity_id)."""
        self._conn.execute(
            """
            INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (entity_id) DO UPDATE SET
                nombre      = excluded.nombre,
                n_docs      = excluded.n_docs,
                n_menciones = excluded.n_menciones,
                alias       = excluded.alias,
                metadata    = excluded.metadata
            """,
            [
                node.entity_id, node.nombre, node.tipo, node.wikidata_id,
                node.n_docs, node.n_menciones,
                json.dumps(node.alias, ensure_ascii=False),
                json.dumps(node.metadata, ensure_ascii=False),
            ],
        )

    def insert_relation(self, edge: RelationEdge) -> int:
        """Inserta una arista con su evidencia y fuentes. Devuelve el id."""
        row = self._conn.execute(
            """
            INSERT INTO relations (figura_slug, origen_id, destino_id, tipo,
                                   fecha, confianza, metodo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                self.slug, edge.origen_id, edge.destino_id, edge.tipo,
                edge.fecha.isoformat(), edge.confianza, edge.metodo,
            ],
        ).fetchone()
        rel_id: int = row[0]

        if edge.evidencia:
            self._conn.executemany(
                "INSERT INTO relation_evidence (relation_id, pasaje) VALUES (?, ?)",
                [(rel_id, p) for p in edge.evidencia],
            )
        if edge.fuentes:
            self._conn.executemany(
                "INSERT INTO relation_sources (relation_id, doc_id) VALUES (?, ?)",
                [(rel_id, d) for d in edge.fuentes],
            )
        return rel_id

    # ── Lectura / queries SQL ──────────────────────────────────────────────

    def entities(self) -> list[dict]:
        """Devuelve todas las entidades del grafo."""
        return self._conn.execute("SELECT * FROM entities").df().to_dict("records")

    def relations(
        self,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        tipo: str | None = None,
        origen_id: str | None = None,
        destino_id: str | None = None,
        min_confianza: float = 0.0,
    ) -> list[dict]:
        """Relaciones con filtros opcionales. Todas las columnas + evidencia."""
        cond:   list[str] = ["r.figura_slug = ?"]
        params: list      = [self.slug]

        if desde:
            cond.append("r.fecha >= ?");   params.append(desde.isoformat())
        if hasta:
            cond.append("r.fecha <= ?");   params.append(hasta.isoformat())
        if tipo:
            cond.append("r.tipo = ?");     params.append(tipo)
        if origen_id:
            cond.append("r.origen_id = ?"); params.append(origen_id)
        if destino_id:
            cond.append("r.destino_id = ?"); params.append(destino_id)
        if min_confianza > 0.0:
            cond.append("r.confianza >= ?"); params.append(min_confianza)

        sql = f"""
            SELECT r.*,
                   e_o.nombre AS origen_nombre,
                   e_d.nombre AS destino_nombre
            FROM relations r
            LEFT JOIN entities e_o ON r.origen_id  = e_o.entity_id
            LEFT JOIN entities e_d ON r.destino_id = e_d.entity_id
            WHERE {" AND ".join(cond)}
            ORDER BY r.fecha
        """
        return self._conn.execute(sql, params).df().to_dict("records")

    def evolucion(self, origen_id: str, destino_id: str) -> list[dict]:
        """Evolución temporal de la relación entre dos entidades."""
        return self.relations(origen_id=origen_id, destino_id=destino_id)

    def resumen_por_tipo(self) -> list[dict]:
        """Conteo de relaciones agrupado por tipo."""
        return self._conn.execute(
            """
            SELECT tipo, COUNT(*) AS n, AVG(confianza) AS confianza_media
            FROM relations
            WHERE figura_slug = ?
            GROUP BY tipo
            ORDER BY n DESC
            """,
            [self.slug],
        ).df().to_dict("records")

    # ── NetworkX ──────────────────────────────────────────────────────────

    def to_networkx(
        self,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        min_confianza: float = 0.0,
    ) -> nx.DiGraph:
        """Construye un grafo dirigido desde las relaciones persistidas.

        Los atributos de entidades y relaciones quedan como metadata de nodos
        y aristas para que las herramientas de visualización los puedan usar.
        """
        G = nx.DiGraph(slug=self.slug)
        for e in self.entities():
            G.add_node(e["entity_id"], **e)
        for r in self.relations(desde=desde, hasta=hasta, min_confianza=min_confianza):
            G.add_edge(r["origen_id"], r["destino_id"], **r)
        return G

    def centralidad(self, **kwargs) -> dict[str, float]:
        """PageRank sobre el grafo — entidades más influyentes."""
        G = self.to_networkx(**kwargs)
        if G.number_of_nodes() == 0:
            return {}
        return nx.pagerank(G)

    def comunidades(self, **kwargs) -> list[set[str]]:
        """Detección de comunidades Louvain sobre el grafo no dirigido."""
        G = self.to_networkx(**kwargs).to_undirected()
        if G.number_of_nodes() == 0:
            return []
        return list(nx.community.louvain_communities(G, seed=42))

    def camino(
        self, origen_id: str, destino_id: str, **kwargs
    ) -> list[str]:
        """Camino más corto entre dos entidades. Lista vacía si no existe."""
        G = self.to_networkx(**kwargs)
        try:
            return nx.shortest_path(G, origen_id, destino_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    # ── Ciclo de vida ─────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "KnowledgeGraph":
        return self

    def __exit__(self, *_) -> None:
        self.close()
