"""Diagnóstico de cardinalidad y calidad del grafo temporal abierto.

Uso (PowerShell):
    $env:PYTHONPATH='.'
    uv run python scripts/inspect_graph.py <slug>

Corre sin cargar todo en memoria: usa SQL agregada sobre DuckDB.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_DATA = Path(os.environ.get("TIMELINE_DATA_DIR", "data"))


def _conn(slug: str):
    import duckdb
    ruta = _DATA / f"graph_{slug}.duckdb"
    if not ruta.exists():
        log.error("no existe %s", ruta)
        log.error("  Genera el grafo con:  uv run python scripts/precompute_tema.py %s", slug)
        sys.exit(1)
    return duckdb.connect(str(ruta), read_only=True)


def _row(con, sql: str, params: list | None = None):
    return con.execute(sql, params or []).fetchone()


def _rows(con, sql: str, params: list | None = None):
    return con.execute(sql, params or []).fetchall()


def _table_exists(con, name: str) -> bool:
    r = _row(con, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name])
    return bool(r and r[0])


def _has_column(con, table: str, column: str) -> bool:
    cols = {r[0] for r in _rows(con, f"DESCRIBE {table}")}
    return column in cols


def main(slug: str) -> None:
    con = _conn(slug)
    sep = "─" * 60

    # ── Resumen general ──────────────────────────────────────────────────────
    n_ent = _row(con, "SELECT COUNT(*) FROM entities")[0]
    n_rel, fmin, fmax = _row(
        con,
        "SELECT COUNT(*), MIN(fecha), MAX(fecha) FROM relations WHERE figura_slug = ?",
        [slug],
    )

    tiene_predicado = _has_column(con, "relations", "predicado")
    tiene_labels = _table_exists(con, "relation_type_labels")

    n_abiertas = n_tipadas = n_labels = 0
    if tiene_predicado:
        n_abiertas = _row(
            con,
            "SELECT COUNT(*) FROM relations WHERE figura_slug = ? AND predicado IS NOT NULL",
            [slug],
        )[0]
        n_tipadas = _row(
            con,
            "SELECT COUNT(*) FROM relations WHERE figura_slug = ? AND tipo IS NOT NULL",
            [slug],
        )[0]

    if tiene_labels:
        n_labels = _row(
            con,
            "SELECT COUNT(*) FROM relation_type_labels WHERE figura_slug = ?",
            [slug],
        )[0]

    log.info("")
    log.info(sep)
    log.info("  Diagnóstico: %s", slug)
    log.info(sep)
    log.info("  Entidades          : %8s", f"{n_ent:,}")
    log.info("  Relaciones totales : %8s", f"{n_rel:,}")
    log.info("  Fecha mínima       : %s", fmin)
    log.info("  Fecha máxima       : %s", fmax)
    if n_rel:
        pct_open = 100 * n_abiertas / n_rel if tiene_predicado else 0
        pct_typed = 100 * n_tipadas / n_rel if tiene_predicado else 0
        pct_null = 100 * (n_rel - n_tipadas) / n_rel if tiene_predicado else 100
        log.info("  Relaciones abiertas: %8s  (%.1f%%)", f"{n_abiertas:,}", pct_open)
        log.info("  Relaciones tipadas : %8s  (%.1f%%)", f"{n_tipadas:,}", pct_typed)
        log.info("  tipo = NULL        : %8s  (%.1f%%)", f"{n_rel - n_tipadas:,}", pct_null)

    # ── Analytics precomputados ──────────────────────────────────────────────
    tiene_centralidad = _table_exists(con, "analytics_centralidad")
    tiene_comunidades = _table_exists(con, "analytics_comunidades")
    if tiene_centralidad or tiene_comunidades:
        n_central = _row(con, "SELECT COUNT(*) FROM analytics_centralidad")[0] if tiene_centralidad else 0
        n_comun_ents = _row(con, "SELECT COUNT(*) FROM analytics_comunidades")[0] if tiene_comunidades else 0
        n_comuns = _row(con, "SELECT COUNT(DISTINCT comunidad_id) FROM analytics_comunidades")[0] if tiene_comunidades else 0
        log.info("")
        log.info("  Analytics precomputados (PageRank + Louvain)")
        log.info("    PageRank: %s entidades indexadas", f"{n_central:,}")
        log.info("    Comunidades: %d comunidades · %s asignaciones", n_comuns, f"{n_comun_ents:,}")
    else:
        log.info("")
        log.info("  Analytics precomputados: NO (ejecuta precompute_tema para generarlos)")

    # ── Etiquetas inducidas ──────────────────────────────────────────────────
    if tiene_labels:
        log.info("")
        log.info("  Etiquetas inducidas (relation_type_labels): %s", f"{n_labels:,}")
        filas = _rows(
            con,
            "SELECT tipo, COUNT(*) AS n FROM relation_type_labels WHERE figura_slug = ? "
            "GROUP BY tipo ORDER BY n DESC",
            [slug],
        )
        for tipo, n in filas:
            log.info("    %-20s %8s", tipo, f"{n:,}")

    # ── Distribución por año ─────────────────────────────────────────────────
    log.info("")
    log.info(sep)
    log.info("  Distribución por año")
    log.info(sep)
    filas = _rows(
        con,
        "SELECT YEAR(fecha) AS anio, COUNT(*) AS n FROM relations "
        "WHERE figura_slug = ? GROUP BY anio ORDER BY anio",
        [slug],
    )
    for anio, n in filas:
        barra = "█" * min(int(n / max(1, (n_rel or 1)) * 40), 40)
        log.info("  %s  %-40s %8s", anio, barra, f"{n:,}")

    # ── Top 20 pares más densos ──────────────────────────────────────────────
    log.info("")
    log.info(sep)
    log.info("  Top 20 pares con más relaciones")
    log.info(sep)
    filas = _rows(
        con,
        """
        SELECT r.origen_id, eo.nombre, r.destino_id, ed.nombre, COUNT(*) AS n
        FROM relations r
        LEFT JOIN entities eo ON r.origen_id = eo.entity_id
        LEFT JOIN entities ed ON r.destino_id = ed.entity_id
        WHERE r.figura_slug = ?
        GROUP BY r.origen_id, eo.nombre, r.destino_id, ed.nombre
        ORDER BY n DESC
        LIMIT 20
        """,
        [slug],
    )
    for i, (oid, on, did, dn, n) in enumerate(filas, 1):
        on = (on or oid)[:28]
        dn = (dn or did)[:28]
        log.info("  %2d. %-28s ↔ %-28s  %6s", i, on, dn, f"{n:,}")

    # ── Top 30 entidades por grado ───────────────────────────────────────────
    log.info("")
    log.info(sep)
    log.info("  Top 30 entidades por grado de incidencia (aristas entrantes + salientes)")
    log.info(sep)
    filas = _rows(
        con,
        """
        SELECT e.entity_id, e.nombre, e.tipo,
               COUNT(r.id) AS grado
        FROM entities e
        LEFT JOIN relations r
               ON (r.origen_id = e.entity_id OR r.destino_id = e.entity_id)
               AND r.figura_slug = ?
        GROUP BY e.entity_id, e.nombre, e.tipo
        ORDER BY grado DESC
        LIMIT 30
        """,
        [slug],
    )
    for i, (eid, nombre, tipo, grado) in enumerate(filas, 1):
        nombre = (nombre or eid)[:35]
        log.info("  %2d. %-35s [%-4s]  grado=%6s", i, nombre, tipo or "?", f"{grado:,}")

    log.info("")
    log.info(sep)
    log.info("")
    con.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    if len(sys.argv) < 2:
        log.error("Uso: python %s <slug>", sys.argv[0])
        sys.exit(1)
    main(sys.argv[1])
