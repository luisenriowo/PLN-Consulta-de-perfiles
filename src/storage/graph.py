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
    tipo        TEXT,                -- categoría (taxonomía); NULL si aún sin tipar
    predicado   TEXT,                -- relación ABIERTA (verbo conector, OpenIE)
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

CREATE TABLE IF NOT EXISTS relation_type_labels (
    relation_id INTEGER PRIMARY KEY,
    figura_slug TEXT    NOT NULL,
    tipo        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rel_slug   ON relations(figura_slug);
CREATE INDEX IF NOT EXISTS idx_rel_origen ON relations(origen_id);
CREATE INDEX IF NOT EXISTS idx_rel_dest   ON relations(destino_id);
CREATE INDEX IF NOT EXISTS idx_rel_fecha  ON relations(fecha);
CREATE INDEX IF NOT EXISTS idx_rel_tipo   ON relations(tipo);

-- Índices compuestos para consultas masivas del frontend/API
CREATE INDEX IF NOT EXISTS idx_rel_slug_fecha_id
    ON relations(figura_slug, fecha, id);

CREATE INDEX IF NOT EXISTS idx_rel_slug_origen_fecha_id
    ON relations(figura_slug, origen_id, fecha, id);

CREATE INDEX IF NOT EXISTS idx_rel_slug_destino_fecha_id
    ON relations(figura_slug, destino_id, fecha, id);

CREATE INDEX IF NOT EXISTS idx_rel_slug_tipo_fecha_id
    ON relations(figura_slug, tipo, fecha, id);

CREATE INDEX IF NOT EXISTS idx_rel_labels_slug_tipo_rel
    ON relation_type_labels(figura_slug, tipo, relation_id);

-- Analíticas precomputadas (centralidad PageRank + comunidades Louvain)
-- Se populan en precompute_tema; la API las lee en O(1) sin cargar NetworkX.
CREATE TABLE IF NOT EXISTS analytics_centralidad (
    entity_id  TEXT PRIMARY KEY,
    pagerank   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_comunidades (
    comunidad_id INTEGER NOT NULL,
    entity_id    TEXT    NOT NULL,
    PRIMARY KEY (comunidad_id, entity_id)
);
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

    # ── Compat esquema viejo/nuevo ─────────────────────────────────────────

    def _has_column(self, table: str, column: str) -> bool:
        """True si la columna existe en la tabla (esquema viejo sin predicado)."""
        cols = {r[0] for r in self._conn.execute(f"DESCRIBE {table}").fetchall()}
        return column in cols

    def _predicado_select(self) -> str:
        """Snippet SQL para la columna `predicado` (r.predicado o NULL AS predicado)."""
        return "r.predicado AS predicado" if self._has_column("relations", "predicado") \
            else "NULL AS predicado"

    def _table_exists(self, name: str) -> bool:
        row = self._conn.execute(
            """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = ?
        """,
            [name],
        ).fetchone()
        assert row is not None
        return bool(row[0])

    def _relation_type_sql(self) -> tuple[str, str]:
        """Devuelve (tipo_expr, join_labels) usando etiquetas inducidas si existen."""
        usar_labels = self._table_exists("relation_type_labels")
        tipo_expr = "COALESCE(rt.tipo, r.tipo)" if usar_labels else "r.tipo"
        join_labels = (
            """
            LEFT JOIN relation_type_labels rt
                ON rt.relation_id = r.id AND rt.figura_slug = r.figura_slug
            """
            if usar_labels
            else ""
        )
        return tipo_expr, join_labels

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
                node.entity_id,
                node.nombre,
                node.tipo,
                node.wikidata_id,
                node.n_docs,
                node.n_menciones,
                json.dumps(node.alias, ensure_ascii=False),
                json.dumps(node.metadata, ensure_ascii=False),
            ],
        )

    def insert_relation(self, edge: RelationEdge) -> int:
        """Inserta una arista con su evidencia y fuentes. Devuelve el id."""
        row = self._conn.execute(
            """
            INSERT INTO relations (figura_slug, origen_id, destino_id, tipo,
                                   predicado, fecha, confianza, metodo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                self.slug,
                edge.origen_id,
                edge.destino_id,
                edge.tipo,
                edge.predicado,
                edge.fecha.isoformat(),
                edge.confianza,
                edge.metodo,
            ],
        ).fetchone()
        assert row is not None
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

    def insert_relations_bulk(self, edges, *, batch_size: int = 10000, on_batch=None) -> int:
        """Inserta muchas aristas en BLOQUE: mucho más rápido que `insert_relation`
        una a una (un commit por lote, no por arista; sin RETURNING por fila).

        Asigna ids EXPLÍCITOS secuenciales en Python (evita el round-trip de
        RETURNING). Pensado para CONSTRUIR un grafo nuevo, donde esta es la única
        vía de inserción y el grafo queda read-only tras el build. Devuelve el
        número de aristas insertadas. `on_batch(total)` se llama tras cada commit
        (para reportar progreso)."""
        import itertools

        nid = (
            self._conn.execute(
                "SELECT coalesce(max(id), 0) FROM relations"
            ).fetchone()[0]
            + 1
        )
        it = iter(edges)
        total = 0
        while True:
            chunk = list(itertools.islice(it, batch_size))
            if not chunk:
                break
            rels, ev, src = [], [], []
            for e in chunk:
                rid = nid
                nid += 1
                rels.append(
                    (
                        rid,
                        self.slug,
                        e.origen_id,
                        e.destino_id,
                        e.tipo,
                        e.predicado,
                        e.fecha.isoformat(),
                        e.confianza,
                        e.metodo,
                    )
                )
                ev.extend((rid, p) for p in e.evidencia)
                src.extend((rid, d) for d in e.fuentes)
            self._conn.execute("BEGIN TRANSACTION")
            self._conn.executemany(
                """INSERT INTO relations (id, figura_slug, origen_id, destino_id,
                       tipo, predicado, fecha, confianza, metodo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rels,
            )
            if ev:
                self._conn.executemany(
                    "INSERT INTO relation_evidence (relation_id, pasaje) VALUES (?, ?)",
                    ev,
                )
            if src:
                self._conn.executemany(
                    "INSERT INTO relation_sources (relation_id, doc_id) VALUES (?, ?)",
                    src,
                )
            self._conn.execute("COMMIT")
            total += len(chunk)
            if on_batch is not None:
                on_batch(total)
        return total

    def update_relation_type(self, relation_id: int, tipo: str | None) -> None:
        """Persiste el tipo inducido/anotado de una arista existente.

        DuckDB no permite actualizar una fila de `relations` si está referenciada
        por `relation_evidence`/`relation_sources`. Guardamos la etiqueta inducida
        en una tabla auxiliar y las lecturas la exponen como `tipo`.
        """
        if tipo is None:
            self._conn.execute(
                "DELETE FROM relation_type_labels WHERE relation_id = ? AND figura_slug = ?",
                [relation_id, self.slug],
            )
            return
        self._conn.execute(
            """
            INSERT INTO relation_type_labels VALUES (?, ?, ?)
            ON CONFLICT (relation_id) DO UPDATE SET
                figura_slug = excluded.figura_slug,
                tipo = excluded.tipo
            """,
            [relation_id, self.slug, tipo],
        )

    # ── Lectura / queries SQL ──────────────────────────────────────────────

    def entities(self) -> list[dict]:
        """Devuelve todas las entidades del grafo."""
        return self._conn.execute("SELECT * FROM entities").df().to_dict("records")

    def entity(self, entity_id: str) -> dict | None:
        """Una entidad por entity_id, o None si no existe."""
        row = self._conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?", [entity_id],
        ).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._conn.description]
        return dict(zip(cols, row))

    def _entities_by_ids(self, ids: "set[str]") -> list[dict]:
        """Resuelve varias entidades en una sola query IN (?,?,…).
        Evita el N+1 de llamar a ``entity()`` por separado (fix B2).
        Devuelve lista (orden estable: como vengan de la BD). Vacío si ids=∅.
        """
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"SELECT * FROM entities WHERE entity_id IN ({placeholders})",
            list(ids),
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, r)) for r in rows]

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
        cond: list[str] = ["r.figura_slug = ?"]
        params: list = [self.slug]
        tipo_expr, join_labels = self._relation_type_sql()

        if desde:
            cond.append("r.fecha >= ?")
            params.append(desde.isoformat())
        if hasta:
            cond.append("r.fecha <= ?")
            params.append(hasta.isoformat())
        if tipo:
            cond.append(f"{tipo_expr} = ?")
            params.append(tipo)
        if origen_id:
            cond.append("r.origen_id = ?")
            params.append(origen_id)
        if destino_id:
            cond.append("r.destino_id = ?")
            params.append(destino_id)
        if min_confianza > 0.0:
            cond.append("r.confianza >= ?")
            params.append(min_confianza)

        sql = f"""
            SELECT r.id,
                   r.figura_slug,
                   r.origen_id,
                   r.destino_id,
                   {tipo_expr} AS tipo,
                   {self._predicado_select()},
                   r.fecha,
                   r.confianza,
                   r.metodo,
                   e_o.nombre AS origen_nombre,
                   e_d.nombre AS destino_nombre
            FROM relations r
            {join_labels}
            LEFT JOIN entities e_o ON r.origen_id  = e_o.entity_id
            LEFT JOIN entities e_d ON r.destino_id = e_d.entity_id
            WHERE {" AND ".join(cond)}
            ORDER BY r.fecha
        """
        rows = self._conn.execute(sql, params).df().to_dict("records")
        for row in rows:
            for key, value in list(row.items()):
                if value != value:  # NaN de pandas para NULL SQL.
                    row[key] = None
        return rows

    def evolucion(self, entidad_a: str, entidad_b: str) -> list[dict]:
        """Evolución temporal de la relación entre dos entidades (ambas
        direcciones, ordenada por fecha). Cada fila trae `predicado` (relación
        abierta), `tipo` (si ya se identificó) y `fecha`: leerlas en orden
        muestra cómo evoluciona el vínculo."""
        ida = self.relations(origen_id=entidad_a, destino_id=entidad_b)
        vuelta = self.relations(origen_id=entidad_b, destino_id=entidad_a)
        return sorted(ida + vuelta, key=lambda r: r["fecha"])

    def evidencia(self, relation_id: int) -> dict:
        """Pasajes de evidencia y doc_ids fuente de una arista (por su id)."""
        pasajes = [
            r[0]
            for r in self._conn.execute(
                "SELECT pasaje FROM relation_evidence WHERE relation_id = ?",
                [relation_id],
            ).fetchall()
        ]
        fuentes = [
            r[0]
            for r in self._conn.execute(
                "SELECT doc_id FROM relation_sources WHERE relation_id = ?",
                [relation_id],
            ).fetchall()
        ]
        return {"pasajes": pasajes, "fuentes": fuentes}

    def resumen_por_tipo(self) -> list[dict]:
        """Conteo de relaciones agrupado por tipo."""
        tipo_expr, join_labels = self._relation_type_sql()
        return (
            self._conn.execute(
                f"""
            SELECT {tipo_expr} AS tipo,
                   COUNT(*) AS n,
                   AVG(r.confianza) AS confianza_media
            FROM relations r
            {join_labels}
            WHERE r.figura_slug = ?
            GROUP BY {tipo_expr}
            ORDER BY n DESC
            """,
                [self.slug],
            )
            .df()
            .to_dict("records")
        )

    def search_entities(self, q: str = "", *, limit: int = 20) -> list[dict]:
        """Búsqueda de entidades por nombre, entity_id o alias.

        - q vacío: top por n_docs DESC, n_menciones DESC (sugerencias iniciales).
        - q no vacío: case-insensitive, ordenado por relevancia:
            1) match exacto en entity_id o nombre;
            2) prefijo;
            3) contiene;
            4) mayor n_docs;
            5) mayor n_menciones.
        `alias` se deserializa defensivamente (puede venir como string JSON).

        Fix B1: el corte top-N se hace en SQL (LIMIT ?) en ambas ramas; la rama
        con `q` además filtra primero en SQL con ILIKE sobre nombre+entity_id+alias
        (candidato acotado, reordenado en Python por relevancia). Alias se parsea
        sólo cuando hay `q` (no se necesita para el top inicial).
        """
        limit = max(1, min(int(limit), 50))
        cols = ["entity_id", "nombre", "tipo", "n_docs", "n_menciones", "alias"]

        def _alias(reg: dict) -> list:
            a = reg.get("alias")
            if isinstance(a, list):
                return a
            if isinstance(a, str):
                try:
                    val = json.loads(a) if a else []
                    return val if isinstance(val, list) else []
                except (json.JSONDecodeError, TypeError):
                    return []
            return []

        qn = (q or "").strip().lower()

        if not qn:
            # Top por n_docs en SQL — no carga toda la tabla en Python.
            filas = self._conn.execute(
                f"SELECT {', '.join(cols)} FROM entities "
                f"ORDER BY n_docs DESC, n_menciones DESC LIMIT ?",
                [limit],
            ).fetchall()
            regs = [dict(zip(cols, r)) for r in filas]
            for r in regs:
                r["alias"] = _alias(r)
            return regs

        # Rama con q: candidato acotado en SQL con ILIKE sobre nombre+entity_id+alias,
        # luego reordenado en Python por (exacto, prefijo, contiene, n_docs).
        like = f"%{qn}%"
        filas = self._conn.execute(
            f"SELECT {', '.join(cols)} FROM entities "
            f"WHERE LOWER(nombre) LIKE ? "
            f"   OR LOWER(entity_id) LIKE ? "
            f"   OR LOWER(CAST(alias AS VARCHAR)) LIKE ? "
            f"ORDER BY n_docs DESC, n_menciones DESC LIMIT ?",
            [like, like, like, max(limit * 5, 50)],
        ).fetchall()
        regs = [dict(zip(cols, r)) for r in filas]
        for r in regs:
            r["alias"] = _alias(r)

        def score(reg: dict) -> tuple:
            nombre = (reg.get("nombre") or "").lower()
            eid = (reg.get("entity_id") or "").lower()
            alias = [str(a).lower() for a in (reg.get("alias") or [])]
            exacto = int(eid == qn or nombre == qn or qn in alias)
            prefijo = int(
                eid.startswith(qn) or nombre.startswith(qn)
                or any(str(a).startswith(qn) for a in alias)
            )
            contiene = int(
                qn in eid or qn in nombre
                or any(qn in str(a) for a in alias)
            )
            return (exacto, prefijo, contiene, reg.get("n_docs") or 0, reg.get("n_menciones") or 0)

        def _match(reg: dict) -> bool:
            nombre = (reg.get("nombre") or "").lower()
            eid = (reg.get("entity_id") or "").lower()
            alias = [str(a).lower() for a in (reg.get("alias") or [])]
            return (
                eid == qn or nombre == qn or qn in alias
                or eid.startswith(qn) or nombre.startswith(qn)
                or any(a.startswith(qn) for a in alias)
                or qn in eid or qn in nombre or any(qn in a for a in alias)
            )

        # Re-valida _match para ordenar/podar con alias ya parseado.
        scored = sorted(regs, key=score, reverse=True)
        out = [r for r in scored if _match(r)]
        return out[:limit]

    def relations_page(
        self,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        tipo: str | None = None,
        origen_id: str | None = None,
        destino_id: str | None = None,
        min_confianza: float = 0.0,
        limit: int = 100,
        offset: int = 0,
        include_total: bool = False,
    ) -> dict:
        """Relaciones con paginación server-side (offset/limit). Columnas
        explícitas + `predicado` siempre presente (NULL si esquema viejo)."""
        cond, params = self._relation_filters(
            desde=desde, hasta=hasta, tipo=tipo, origen_id=origen_id,
            destino_id=destino_id, min_confianza=min_confianza,
        )
        where = " AND ".join(cond)
        tipo_expr, join_labels = self._relation_type_sql()
        total: int | None = None
        if include_total:
            total = int(self._conn.execute(
                f"SELECT COUNT(*) FROM relations r {join_labels} WHERE {where}", params,
            ).fetchone()[0])

        sql = f"""
            SELECT r.id, r.figura_slug, r.origen_id, r.destino_id, {tipo_expr} AS tipo,
                   {self._predicado_select()},
                   r.fecha, r.confianza, r.metodo,
                   e_o.nombre AS origen_nombre,
                   e_d.nombre AS destino_nombre
            FROM relations r
            {join_labels}
            LEFT JOIN entities e_o ON r.origen_id  = e_o.entity_id
            LEFT JOIN entities e_d ON r.destino_id = e_d.entity_id
            WHERE {where}
            ORDER BY r.fecha, r.id
            LIMIT ? OFFSET ?
        """
        params_p = params + [limit, offset]
        items = self._rows(self._conn.execute(sql, params_p))
        for it in items:
            it.setdefault("predicado", None)
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _relation_filters(
        self,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        tipo: str | None = None,
        origen_id: str | None = None,
        destino_id: str | None = None,
        min_confianza: float = 0.0,
    ) -> tuple[list[str], list]:
        """Construye WHERE compartido para relations. Devuelve (cláusulas, params)."""
        cond: list[str] = ["r.figura_slug = ?"]
        params: list = [self.slug]
        if desde:
            cond.append("r.fecha >= ?"); params.append(desde.isoformat())
        if hasta:
            cond.append("r.fecha <= ?"); params.append(hasta.isoformat())
        if tipo:
            tipo_expr, _ = self._relation_type_sql()
            cond.append(f"{tipo_expr} = ?"); params.append(tipo)
        if origen_id:
            cond.append("r.origen_id = ?"); params.append(origen_id)
        if destino_id:
            cond.append("r.destino_id = ?"); params.append(destino_id)
        if min_confianza > 0.0:
            cond.append("r.confianza >= ?"); params.append(min_confianza)
        return cond, params

    @staticmethod
    def _rows(cur) -> list[dict]:
        """Convierte cursor DuckDB en lista de dicts con fechas ISO."""
        cols = [d[0] for d in cur.description]
        out = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            f = d.get("fecha")
            if isinstance(f, date):
                d["fecha"] = f.isoformat()
            out.append(d)
        return out

    def evolucion_filtrada(
        self,
        entidad_a: str,
        entidad_b: str,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        tipo: str | None = None,
        min_confianza: float = 0.0,
        limit: int | None = None,
    ) -> dict:
        """Evolución temporal bidireccional entre dos entidades en una sola query
        SQL (ambas direcciones + filtros fecha/tipo/confianza). `predicado`
        siempre presente (NULL si esquema viejo).

        Fix B3: si ``limit`` no es None, se aplica ``LIMIT limit+1`` en SQL para
        detectar truncamiento y se devuelve un dict ``{items, truncado, limit}``;
        si ``limit`` es None, se devuelven todas las filas (comportamiento
        legacy) en un dict ``{items, truncado: False, limit: None}``.
        """
        cond, params = self._relation_filters(
            desde=desde, hasta=hasta, tipo=tipo, min_confianza=min_confianza,
        )
        cond.append(
            "((r.origen_id = ? AND r.destino_id = ?) "
            "OR (r.origen_id = ? AND r.destino_id = ?))"
        )
        params.extend([entidad_a, entidad_b, entidad_b, entidad_a])
        tipo_expr, join_labels = self._relation_type_sql()

        sql = f"""
            SELECT r.id, r.figura_slug, r.origen_id, r.destino_id, {tipo_expr} AS tipo,
                   {self._predicado_select()},
                   r.fecha, r.confianza, r.metodo,
                   e_o.nombre AS origen_nombre,
                   e_d.nombre AS destino_nombre
            FROM relations r
            {join_labels}
            LEFT JOIN entities e_o ON r.origen_id  = e_o.entity_id
            LEFT JOIN entities e_d ON r.destino_id = e_d.entity_id
            WHERE {" AND ".join(cond)}
            ORDER BY r.fecha, r.id
        """
        if limit is not None:
            limit = max(1, min(int(limit), 2000))
            sql = sql + " LIMIT ?"
            params = params + [limit + 1]
        rows = self._rows(self._conn.execute(sql, params))
        truncado = limit is not None and len(rows) > limit
        items = rows[:limit] if (limit is not None and truncado) else rows
        for it in items:
            it.setdefault("predicado", None)
        return {"items": items, "truncado": truncado, "limit": limit}

    def ego(
        self,
        entity_id: str,
        *,
        profundidad: int = 1,
        desde: date | None = None,
        hasta: date | None = None,
        tipo: str | None = None,
        min_confianza: float = 0.0,
        limit: int = 500,
    ) -> dict:
        """Ego-grafo on-demand de `entity_id` (debe existir).

        profundidad=1: incidentes al centro en SQL (LIMIT limit+1).
        profundidad=2: suma incidentes a los vecinos directos.
        Filtros (desde/hasta/tipo/min_confianza) van al WHERE; LIMIT va temprano.
        `truncado=True` si se pidió limit+1 y llegaron más de `limit` filas.
        Deduplica por `r.id` (una arista centro↔vecino aparece en ambos pasos).
        No llama a `self.relations(...)` sin filtro de entidad.
        """
        if profundidad not in (1, 2):
            profundidad = 1
        limit = max(1, min(int(limit), 2000))

        cond_base, params_base = self._relation_filters(
            desde=desde, hasta=hasta, tipo=tipo, min_confianza=min_confianza,
        )
        tipo_expr, join_labels = self._relation_type_sql()

        def _ego_select(extra_cond: list[str], extra_params: list, lim: int) -> list[dict]:
            cond = list(cond_base) + extra_cond
            params = list(params_base) + extra_params
            sql = f"""
                SELECT r.id, r.figura_slug, r.origen_id, r.destino_id, {tipo_expr} AS tipo,
                       {self._predicado_select()},
                       r.fecha, r.confianza, r.metodo,
                       e_o.nombre AS origen_nombre,
                       e_d.nombre AS destino_nombre
                FROM relations r
                {join_labels}
                LEFT JOIN entities e_o ON r.origen_id  = e_o.entity_id
                LEFT JOIN entities e_d ON r.destino_id = e_d.entity_id
                WHERE {" AND ".join(cond)}
                ORDER BY r.fecha, r.id
                LIMIT ?
            """
            return self._rows(self._conn.execute(sql, params + [lim]))

        # p=1: incidentes al centro (LIMIT limit+1 para detectar truncamiento).
        # Sólo se ingieren las primeras `limit` filas; la limit+1-ésima se
        # descarta y NO contamina entidades/vecinos (fix A1).
        rows_p1 = _ego_select(
            ["(r.origen_id = ? OR r.destino_id = ?)"], [entity_id, entity_id],
            lim=limit + 1,
        )
        truncado_p1 = len(rows_p1) > limit
        rows_p1 = rows_p1[:limit]

        vistos: set[int] = set()
        incidentes: list[dict] = []
        vecinos: set[str] = set()

        def _ingest(rows: list[dict]) -> None:
            for r in rows:
                rid = r.get("id")
                if rid is not None and rid in vistos:
                    continue
                if rid is not None:
                    vistos.add(rid)
                incidentes.append(r)
                vecinos.add(r["origen_id"]); vecinos.add(r["destino_id"])

        _ingest(rows_p1)
        vecinos.discard(entity_id)

        # p=2: incidentes a vecinos (cupo = limit+1 siempre, se dedup por id)
        truncado_p2 = False
        if profundidad == 2 and vecinos:
            placeholders = ",".join("?" for _ in vecinos)
            cond_v = [f"(r.origen_id IN ({placeholders}) OR r.destino_id IN ({placeholders}))"]
            params_v = list(vecinos) + list(vecinos)
            rows_p2 = _ego_select(cond_v, params_v, lim=limit + 1)
            truncado_p2 = len(rows_p2) > limit
            _ingest(rows_p2[:limit])

        # Orden estable (fecha, id) y slice final a `limit`.
        todas = sorted(incidentes, key=lambda r: (str(r["fecha"]), r.get("id") or 0))
        truncado = truncado_p1 or truncado_p2 or len(todas) > limit
        relaciones_out = todas[:limit]
        for r in relaciones_out:
            r.setdefault("predicado", None)

        # Entidades = exactamente las que aparecen en relaciones_out + el centro.
        # Se reconstruyen desde relaciones_out para evitar contaminación por la
        # fila sentinel (fix A1). Resueltas en una sola query IN (?,?,…) (fix B2).
        entidades_ids: set[str] = {entity_id}
        for r in relaciones_out:
            entidades_ids.add(r["origen_id"])
            entidades_ids.add(r["destino_id"])
        entidades = self._entities_by_ids(entidades_ids)

        return {
            "centro": entity_id,
            "profundidad": profundidad,
            "entidades": entidades,
            "relaciones": relaciones_out,
            "truncado": truncado,
            "limit": limit,
        }

    # ── Stats (C6) ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Conteos rápidos para que el frontend decida si cargar todo el grafo."""
        n_ent = int(self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
        n_rel, fmin, fmax = self._conn.execute(
            "SELECT COUNT(*), MIN(fecha), MAX(fecha) "
            "FROM relations WHERE figura_slug = ?", [self.slug],
        ).fetchone()
        return {
            "n_entidades": n_ent,
            "n_relaciones": int(n_rel or 0),
            "fecha_min": fmin.isoformat() if fmin else None,
            "fecha_max": fmax.isoformat() if fmax else None,
        }

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

    def precompute_analytics(self) -> dict:
        """Precomputa PageRank y comunidades Louvain sobre el grafo completo y los
        persiste en DuckDB. Llamar al final de precompute_tema (modo write).

        Para grafos masivos evita cargar NetworkX en cada request de la API:
        la carga se hace una sola vez offline y las lecturas son O(n) SQL.
        """
        from collections import defaultdict

        G = self.to_networkx()
        n_nodos = G.number_of_nodes()
        n_aristas = G.number_of_edges()
        if n_nodos == 0:
            return {"n_nodos": 0, "n_aristas": 0, "n_comunidades": 0}

        pr = nx.pagerank(G)
        self._conn.execute("DELETE FROM analytics_centralidad")
        self._conn.executemany(
            "INSERT INTO analytics_centralidad (entity_id, pagerank) VALUES (?, ?)",
            list(pr.items()),
        )

        G_u = G.to_undirected()
        comms = list(nx.community.louvain_communities(G_u, seed=42))
        self._conn.execute("DELETE FROM analytics_comunidades")
        rows = [
            (cid, eid)
            for cid, comm in enumerate(comms)
            for eid in comm
        ]
        if rows:
            self._conn.executemany(
                "INSERT INTO analytics_comunidades (comunidad_id, entity_id) VALUES (?, ?)",
                rows,
            )

        return {"n_nodos": n_nodos, "n_aristas": n_aristas, "n_comunidades": len(comms)}

    @staticmethod
    def _sin_filtros(desde: "date | None", hasta: "date | None", min_confianza: float) -> bool:
        """True cuando los parámetros no acotan el grafo — condición para usar el precompute."""
        return desde is None and hasta is None and min_confianza == 0.0

    def centralidad(
        self,
        *,
        desde: "date | None" = None,
        hasta: "date | None" = None,
        min_confianza: float = 0.0,
    ) -> dict[str, float]:
        """PageRank: lee el precompute global si no hay filtros efectivos; live si los hay."""
        if self._sin_filtros(desde, hasta, min_confianza) and self._table_exists("analytics_centralidad"):
            rows = self._conn.execute(
                "SELECT entity_id, pagerank FROM analytics_centralidad"
            ).fetchall()
            if rows:
                return dict(rows)
        G = self.to_networkx(desde=desde, hasta=hasta, min_confianza=min_confianza)
        if G.number_of_nodes() == 0:
            return {}
        return nx.pagerank(G)

    def comunidades(
        self,
        *,
        desde: "date | None" = None,
        hasta: "date | None" = None,
        min_confianza: float = 0.0,
    ) -> list[set[str]]:
        """Comunidades Louvain: lee el precompute global si no hay filtros efectivos; live si los hay."""
        if self._sin_filtros(desde, hasta, min_confianza) and self._table_exists("analytics_comunidades"):
            rows = self._conn.execute(
                "SELECT comunidad_id, entity_id FROM analytics_comunidades"
            ).fetchall()
            if rows:
                from collections import defaultdict
                grupos: dict[int, set[str]] = defaultdict(set)
                for cid, eid in rows:
                    grupos[cid].add(eid)
                return list(grupos.values())
        G = self.to_networkx(desde=desde, hasta=hasta, min_confianza=min_confianza).to_undirected()
        if G.number_of_nodes() == 0:
            return []
        return list(nx.community.louvain_communities(G, seed=42))

    def cambios_relacion(self, top_n: int = 20) -> list[dict]:
        """Pares con más de un tipo de relación a lo largo del tiempo.

        Usa SQL puro — no carga NetworkX. Detecta pares donde el tipo dominante
        cambia (p. ej. alianza→conflicto). Devuelve los top_n pares ordenados por
        número de tipos distintos, cada uno con su secuencia temporal de tipos.
        Solo opera sobre relaciones tipadas (tipo IS NOT NULL).
        """
        top_n = max(1, min(int(top_n), 100))
        tipo_expr, join_labels = self._relation_type_sql()

        sql_top = f"""
            WITH typed_rels AS (
                SELECT r.origen_id, r.destino_id, r.fecha, {tipo_expr} AS tipo
                FROM relations r
                {join_labels}
                WHERE r.figura_slug = ? AND {tipo_expr} IS NOT NULL
            ),
            pares AS (
                SELECT LEAST(origen_id, destino_id)    AS ent_a,
                       GREATEST(origen_id, destino_id) AS ent_b,
                       tipo,
                       MIN(fecha)  AS primera,
                       MAX(fecha)  AS ultima,
                       COUNT(*)    AS n
                FROM typed_rels
                GROUP BY LEAST(origen_id, destino_id),
                         GREATEST(origen_id, destino_id),
                         tipo
            ),
            transiciones AS (
                SELECT ent_a, ent_b,
                       COUNT(DISTINCT tipo)  AS n_tipos,
                       SUM(n)                AS n_relaciones,
                       MIN(primera)          AS fecha_inicio,
                       MAX(ultima)           AS fecha_fin
                FROM pares
                GROUP BY ent_a, ent_b
                HAVING COUNT(DISTINCT tipo) > 1
            )
            SELECT t.ent_a, ea.nombre AS nombre_a,
                   t.ent_b, eb.nombre AS nombre_b,
                   t.n_tipos, t.n_relaciones, t.fecha_inicio, t.fecha_fin
            FROM transiciones t
            LEFT JOIN entities ea ON t.ent_a = ea.entity_id
            LEFT JOIN entities eb ON t.ent_b = eb.entity_id
            ORDER BY t.n_tipos DESC, t.n_relaciones DESC
            LIMIT ?
        """
        filas = self._conn.execute(sql_top, [self.slug, top_n]).fetchall()

        sql_seq = f"""
            SELECT {tipo_expr} AS tipo,
                   MIN(r.fecha) AS primera, MAX(r.fecha) AS ultima, COUNT(*) AS n
            FROM relations r
            {join_labels}
            WHERE r.figura_slug = ?
              AND ((r.origen_id = ? AND r.destino_id = ?)
                OR (r.origen_id = ? AND r.destino_id = ?))
              AND {tipo_expr} IS NOT NULL
            GROUP BY ({tipo_expr})
            ORDER BY primera
        """
        out = []
        for ent_a, nombre_a, ent_b, nombre_b, n_tipos, n_rel, f_inicio, f_fin in filas:
            seq = self._conn.execute(
                sql_seq, [self.slug, ent_a, ent_b, ent_b, ent_a]
            ).fetchall()
            out.append({
                "entidad_a": ent_a,
                "nombre_a": nombre_a or ent_a,
                "entidad_b": ent_b,
                "nombre_b": nombre_b or ent_b,
                "n_tipos": int(n_tipos),
                "n_relaciones": int(n_rel),
                "fecha_inicio": str(f_inicio) if f_inicio else None,
                "fecha_fin": str(f_fin) if f_fin else None,
                "secuencia": [
                    {"tipo": t, "primera": str(p), "ultima": str(u), "n": int(n)}
                    for t, p, u, n in seq
                ],
            })
        return out

    def camino(self, origen_id: str, destino_id: str, **kwargs) -> list[str]:
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
