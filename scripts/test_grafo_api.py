r"""Tests de la API de grafo P4 (endpoints nuevos: buscar, evolucion, ego, pagina).

Corre sobre el grafo semilla local `data/graph_humala.duckdb` si existe; si no,
construye una BD temporal minima con un par de entidades y relaciones para no
depender de precomputo previo. Usa TestClient de FastAPI (sin levantar server).

Uso:
    $env:PYTHONPATH='.'
    .\.venv\Scripts\python.exe scripts/test_grafo_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# Reservar un tmp dir ANTES de importar src.storage para que graph.py lo use.
_TMP = Path(tempfile.mkdtemp(prefix="test_grafo_api_"))
os.environ["TIMELINE_DATA_DIR"] = str(_TMP)

# Asegurar manifiesto minimo en el tmp dir para que _check_slug no bloquee.
_MAN = _TMP / "figuras.json"
_MAN.write_text(
    '[{"slug":"humala","nombre":"Ollanta Humala","rango_fechas":'
    '["2021-01-26","2026-01-15"],"n_eventos":1}]',
    encoding="utf-8",
)
os.environ.setdefault("TIMELINE_DATA_DIR", str(_TMP))

# Asegurar que el cwd esta en sys.path para el import `src.*` cuando se corre
# desde cualquier lado.
_CWD = Path(__file__).resolve().parent.parent
if str(_CWD) not in sys.path:
    sys.path.insert(0, str(_CWD))

# Ahora si imports del proyecto
from fastapi.testclient import TestClient          # noqa: E402
from src.app.api import app                        # noqa: E402
from src.schemas import EntityNode, RelationEdge   # noqa: E402
from src.storage import KnowledgeGraph             # noqa: E402

SLUG = "humala"


def _hay_grafo_real() -> bool:
    """True si existe el grafo semilla en el directorio data/ default."""
    # graph.py respeta TIMELINE_DATA_DIR; pero el grafo real esta en data/
    real = Path(_CWD) / "data" / f"graph_{SLUG}.duckdb"
    return real.exists()


def _seed_temporal() -> None:
    """Si no hay grafo real, construye uno minimo en el tmp dir."""
    with KnowledgeGraph(SLUG) as g:
        g.upsert_entity(EntityNode(
            entity_id="ollanta-humala", nombre="Ollanta Humala", tipo="PER",
            n_docs=88, n_menciones=409, alias=["Humala"],
        ))
        g.upsert_entity(EntityNode(
            entity_id="nadine-heredia", nombre="Nadine Heredia", tipo="PER",
            n_docs=65, n_menciones=120, alias=["Nadine"],
        ))
        g.upsert_entity(EntityNode(
            entity_id="partido-nacionalista", nombre="Partido Nacionalista",
            tipo="ORG", n_docs=42, n_menciones=70, alias=["PN"],
        ))
        g.insert_relation(RelationEdge(
            origen_id="ollanta-humala", destino_id="nadine-heredia",
            tipo="acusacion", fecha=date(2021, 1, 26),
            confianza=0.82, metodo="rules",
        ))
        g.insert_relation(RelationEdge(
            origen_id="nadine-heredia", destino_id="ollanta-humala",
            tipo="mencion", fecha=date(2022, 3, 15),
            confianza=0.5, metodo="rules",
        ))
        g.insert_relation(RelationEdge(
            origen_id="ollanta-humala", destino_id="partido-nacionalista",
            tipo="pertenencia", fecha=date(2021, 6, 1),
            confianza=0.9, metodo="rules",
        ))


def _run() -> int:
    fallos = 0

    def check(nombre: str, cond: bool, extra: str = "") -> None:
        nonlocal fallos
        if cond:
            print(f"  OK  {nombre}")
        else:
            fallos += 1
            print(f" FAIL  {nombre}  {extra}")

    if not _hay_grafo_real():
        print(f"[setup] No hay data/graph_{SLUG}.duckdb; sembrando grafo temporal")
        _seed_temporal()
    else:
        # Copiar el grafo real al tmp dir para que TIMELINE_DATA_DIR lo encuentre
        # (graph.py abre <TIMELINE_DATA_DIR>/graph_<slug>.duckdb).
        import shutil
        shutil.copyfile(
            _CWD / "data" / f"graph_{SLUG}.duckdb",
            _TMP / f"graph_{SLUG}.duckdb",
        )
        # Necesita un corpus para _fuentes_map -- sin corpus, los endpoints que
        # lo usan (solo evidencia) no se testean aqui.
        print(f"[setup] Grafo real copiado a {_TMP / ('graph_' + SLUG + '.duckdb')}")

    c = TestClient(app)

    print("\n[1] /entidades/buscar -- encuentra Ollanta Humala")
    r = c.get(f"/api/figuras/{SLUG}/grafo/entidades/buscar?q=Humala")
    check("status 200", r.status_code == 200, str(r.status_code))
    body = r.json()
    check("es lista", isinstance(body, list))
    check("no vacio", len(body) > 0)
    check(
        "encuentra ollanta-humala",
        any(e.get("entity_id") == "ollanta-humala" for e in body),
        str([e.get("entity_id") for e in body[:5]]),
    )
    # alias deserializado
    ollanta = next((e for e in body if e.get("entity_id") == "ollanta-humala"), {})
    check("alias es lista", isinstance(ollanta.get("alias"), list),
          str(type(ollanta.get("alias"))))

    print("\n[2] /entidades/buscar?q= (vacio) -- top por n_docs, sin error")
    r = c.get(f"/api/figuras/{SLUG}/grafo/entidades/buscar?q=&limit=5")
    check("status 200", r.status_code == 200, str(r.status_code))

    print("\n[2b] /entidades/buscar?q=zzzz-noexiste -- [] (no devuelve top enganoso)")
    r = c.get(f"/api/figuras/{SLUG}/grafo/entidades/buscar?q=zzzz-noexiste")
    check("status 200", r.status_code == 200, str(r.status_code))
    check("lista vacia", r.json() == [], str(r.json())[:120])

    print("\n[2c] /entidades/buscar -- busca tambien por alias puro")
    r = c.get(f"/api/figuras/{SLUG}/grafo/entidades/buscar?q=Equipo%20Especial")
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        ids_alias = {e.get("entity_id") for e in r.json()}
        check("encuentra alias Equipo Especial",
              "lava-jato" in ids_alias,
              str(list(ids_alias)[:10]))

    print("\n[3] /ego/ollanta-humala -- trae la entidad central")
    r = c.get(f"/api/figuras/{SLUG}/grafo/ego/ollanta-humala")
    check("status 200", r.status_code == 200, str(r.text[:300]))
    if r.status_code == 200:
        body = r.json()
        check("centro coincide", body.get("centro") == "ollanta-humala",
              str(body.get("centro")))
        ids = [e.get("entity_id") for e in body.get("entidades", [])]
        check("centro en entidades", "ollanta-humala" in ids, str(ids))
        check("profundidad=1 default", body.get("profundidad") == 1)
        # predicado presente (null si esquema viejo)
        rels = body.get("relaciones", [])
        if rels:
            check("predicado presente", "predicado" in rels[0],
                  str(list(rels[0].keys())[:10]))

    print("\n[4] /ego de entidad inexistente -- 404")
    r = c.get(f"/api/figuras/{SLUG}/grafo/ego/no-existe-12345")
    check("status 404", r.status_code == 404, str(r.status_code))

    print("\n[5] /evolucion ollanta-humala <-> nadine-heredia -- lista ordenada")
    r = c.get(
        f"/api/figuras/{SLUG}/grafo/evolucion"
        f"?entidad_a=ollanta-humala&entidad_b=nadine-heredia"
    )
    check("status 200", r.status_code == 200, str(r.text[:300]))
    if r.status_code == 200:
        body = r.json()
        check(
            "entidad_a bien",
            body.get("entidad_a", {}).get("entity_id") == "ollanta-humala",
        )
        evs = body.get("eventos", [])
        if evs:
            fechas = [e.get("fecha") for e in evs]
            check("ordenadas asc", fechas == sorted(fechas), str(fechas))
            check("predicado presente", "predicado" in evs[0])
        # bidireccional: con el grafo real hay al menos 1; con el temporal 2
        check("algun evento", len(evs) >= 1, str(len(evs)))

    print("\n[6] /evolucion -- entidad no existe -> 404")
    r = c.get(
        f"/api/figuras/{SLUG}/grafo/evolucion"
        f"?entidad_a=no-existe&entidad_b=nadine-heredia"
    )
    check("status 404", r.status_code == 404, str(r.status_code))

    print("\n[7] /relaciones/pagina -- respeta limit y trae total/items")
    r = c.get(
        f"/api/figuras/{SLUG}/grafo/relaciones/pagina?limit=10&offset=0"
        f"&include_total=true"
    )
    check("status 200", r.status_code == 200, str(r.text[:300]))
    if r.status_code == 200:
        body = r.json()
        check("tiene items", isinstance(body.get("items"), list))
        check("limit en respaldo", body.get("limit") == 10, str(body.get("limit")))
        check("offset en respaldo", body.get("offset") == 0)
        check("total presente", body.get("total") is not None,
              str(body.get("total")))
        check("items <= limit", len(body.get("items", [])) <= 10)

    # offset > 0 debe dar una pagina distinta (o vacia si el total es chico)
    r2 = c.get(
        f"/api/figuras/{SLUG}/grafo/relaciones/pagina?limit=5&offset=1000"
    )
    check("offset grande -> 200 vacio", r2.status_code == 200 and
          len(r2.json().get("items", [])) == 0, str(r2.status_code))

    print("\n[8] Fechas invalidas -> 400")
    r = c.get(
        f"/api/figuras/{SLUG}/grafo/relaciones/pagina?desde=no-es-fecha"
    )
    check("status 400", r.status_code == 400, str(r.status_code))
    r = c.get(
        f"/api/figuras/{SLUG}/grafo/evolucion"
        f"?entidad_a=ollanta-humala&entidad_b=nadine-heredia&desde=abc"
    )
    check("evolucion 400 con fecha mala", r.status_code == 400, str(r.status_code))

    print("\n[9] /relaciones (legacy) sigue funcionando")
    r = c.get(f"/api/figuras/{SLUG}/grafo/relaciones?limit=5")
    check("status 200", r.status_code == 200, str(r.status_code))
    check("es lista", isinstance(r.json(), list))

    print("\n[10] /grafo/stats -- conteos y claves")
    r = c.get(f"/api/figuras/{SLUG}/grafo/stats")
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        s = r.json()
        for k in ("n_entidades", "n_relaciones", "fecha_min", "fecha_max"):
            check(f"tiene {k}", k in s, str(list(s.keys())))
        check("n_relaciones int > 0", isinstance(s.get("n_relaciones"), int)
              and s["n_relaciones"] > 0, str(s.get("n_relaciones")))

    print("\n[11] /relaciones/pagina -- predicado siempre presente por item")
    r = c.get(f"/api/figuras/{SLUG}/grafo/relaciones/pagina?limit=10")
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        items = r.json().get("items", [])
        if items:
            check("items con predicado", all("predicado" in it for it in items),
                  str([list(it.keys())[:8] for it in items[:1]]))
        else:
            check("items con predicado (vacio, skip)", True)

    print("\n[12] /ego -- predicado presente + limit se respeta")
    r = c.get(f"/api/figuras/{SLUG}/grafo/ego/ollanta-humala?limit=5")
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        body = r.json()
        rels = body.get("relaciones", [])
        if rels:
            check("ego items con predicado", all("predicado" in it for it in rels))
            check("ego respeta limit", len(rels) <= 5, str(len(rels)))
        # truncado flag presente
        check("ego trunca flag", "truncado" in body, str(body.keys()))

    print("\n[13] /ego profundidad=2 -- no duplica relaciones por id")
    r = c.get(f"/api/figuras/{SLUG}/grafo/ego/ollanta-humala?profundidad=2&limit=200")
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        rels = r.json().get("relaciones", [])
        ids = [r.get("id") for r in rels if r.get("id") is not None]
        check("ego p=2 sin ids dup", len(ids) == len(set(ids)),
              f"{len(ids)} ids, {len(set(ids))} unicos")

    print("\n[14] Test estructural -- ego() no carga todas las relaciones")
    import inspect
    from src.storage.graph import KnowledgeGraph as _KG
    src_ego = inspect.getsource(_KG.ego)
    check("ego no usa relations() sin filtro", "rels_all = self.relations" not in src_ego,
          "ego aun carga todo relations()")

    print("\n[15] ego limit+1 truncamiento")
    # limit=1 en ollanta-humala (suele tener >1 incidente)
    r = c.get(f"/api/figuras/{SLUG}/grafo/ego/ollanta-humala?limit=1")
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        body = r.json()
        # Si hay mas de 1 incidente, truncado=True y relaciones=1
        if body.get("relaciones"):
            check("ego limit=1 da <=1 rel", len(body["relaciones"]) <= 1,
                  str(len(body["relaciones"])))

    print("\n[16] A1: entidades del ego coinciden con las aristas retornadas")
    # Para limit y profundidad variables, entidades debe ser exactamente el
    # subconjunto de nodos presentes en relaciones + el centro. Si hay
    # contaminacion por la fila sentinel, aparecen entidades extra.
    for lim, prof in [(5, 1), (10, 2), (3, 1)]:
        r = c.get(
            f"/api/figuras/{SLUG}/grafo/ego/ollanta-humala"
            f"?limit={lim}&profundidad={prof}"
        )
        if r.status_code != 200:
            check(f"[lim={lim},p={prof}] status 200", False, str(r.status_code))
            continue
        body = r.json()
        rels = body.get("relaciones", [])
        ids_en_rels = {body["centro"]}
        for r_ in rels:
            ids_en_rels.add(r_["origen_id"])
            ids_en_rels.add(r_["destino_id"])
        ids_entidades = {e["entity_id"] for e in body.get("entidades", [])}
        check(f"[lim={lim},p={prof}] entidades==rels",
              ids_entidades == ids_en_rels,
              f"entidades={len(ids_entidades)} vs esperado={len(ids_en_rels)}")
        # Invariante: |relaciones| <= limit  y  truncado flag presente
        check(f"[lim={lim},p={prof}] |rels|<=limit",
              len(rels) <= lim, str(len(rels)))
        check(f"[lim={lim},p={prof}] limite en respaldo",
              body.get("limit") == lim, str(body.get("limit")))

    print("\n[17] A2: paginacion sin duplicados ni saltos (union == total)")
    # Iterar paginas con limit=K, reunir ids, y comparar con total.
    K = 2
    total = None
    todos_ids = []
    offset = 0
    while True:
        r = c.get(
            f"/api/figuras/{SLUG}/grafo/relaciones/pagina"
            f"?limit={K}&offset={offset}&include_total=true"
        )
        if r.status_code != 200:
            check("pagina iteration status 200", False, str(r.status_code))
            break
        body = r.json()
        if total is None:
            total = body.get("total")
        page = body.get("items", [])
        if not page:
            break
        todos_ids.extend(it["id"] for it in page)
        offset += K
        # Seguro anti loop infinito
        if offset > 10000:
            break
    if total is not None:
        check("union ids == total",
              len(todos_ids) == total,
              f"recogidos={len(todos_ids)} vs total={total}")
        check("sin ids duplicados entre paginas",
              len(todos_ids) == len(set(todos_ids)),
              f"unicos={len(set(todos_ids))} vs total={len(todos_ids)}")

    print("\n[18] A2: orden estable entre llamadas (r.fecha, r.id)")
    # Pedir la misma pagina dos veces y comparar que el orden de ids sea identico.
    r1 = c.get(f"/api/figuras/{SLUG}/grafo/relaciones/pagina?limit=20&offset=0")
    r2 = c.get(f"/api/figuras/{SLUG}/grafo/relaciones/pagina?limit=20&offset=0")
    if r1.status_code == 200 and r2.status_code == 200:
        ids1 = [it["id"] for it in r1.json().get("items", [])]
        ids2 = [it["id"] for it in r2.json().get("items", [])]
        check("orden estable entre 2 llamadas", ids1 == ids2,
              f"ids1={ids1[:5]} ids2={ids2[:5]}")
        # Y las fechas deben estar ordenadas
        fechas = [it.get("fecha") for it in r1.json().get("items", [])]
        check("fechas asc",
              fechas == sorted(fechas, key=lambda x: x or ""),
              str(fechas[:5]))

    print("\n[19] /evolucion bidireccional (A.B y B.A devuelven mismo set)")
    url_a = (f"/api/figuras/{SLUG}/grafo/evolucion"
             f"?entidad_a=ollanta-humala&entidad_b=nadine-heredia")
    url_b = (f"/api/figuras/{SLUG}/grafo/evolucion"
             f"?entidad_a=nadine-heredia&entidad_b=ollanta-humala")
    r_a = c.get(url_a)
    r_b = c.get(url_b)
    check("A->B status 200", r_a.status_code == 200, str(r_a.status_code))
    check("B->A status 200", r_b.status_code == 200, str(r_b.status_code))
    if r_a.status_code == 200 and r_b.status_code == 200:
        evs_a = r_a.json().get("eventos", [])
        evs_b = r_b.json().get("eventos", [])
        # Clave por (fecha, id) — id unico, no importa el orden de a/b.
        keys_a = {(e.get("fecha"), e.get("id")) for e in evs_a}
        keys_b = {(e.get("fecha"), e.get("id")) for e in evs_b}
        check("bidireccional: mismo conjunto de eventos",
              keys_a == keys_b,
              f"A={len(keys_a)} B={len(keys_b)}")
        # truncado/limit presentes (B3)
        check("evolucion tiene truncado flag",
              "truncado" in r_a.json(),
              str(r_a.json().keys()))
        check("evolucion tiene limit", r_a.json().get("limit") is not None,
              str(r_a.json().get("limit")))

    print("\n[20] A3 + B3: predicado abierto renderizable + truncado evolucion")
    # Si la BD semilla tiene esquema nuevo, sembramos una relacion abierta
    # (tipo=null, predicado="acusó") en el grafo temporal para probar el
    # predicado. Si el grafo real no la tiene, igual verificamos que el campo
    # predicado este presente en cada item (null o verbo).
    r = c.get(
        f"/api/figuras/{SLUG}/grafo/evolucion"
        f"?entidad_a=ollanta-humala&entidad_b=nadine-heredia&limit=1"
    )
    check("status 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        body = r.json()
        evs = body.get("eventos", [])
        if evs:
            check("predicado presente en evento",
                  "predicado" in evs[0],
                  str(list(evs[0].keys())[:10]))
            # Con limit=1: limit==1, truncado flag informado (True o False)
            check("limit=1 respetado", body.get("limit") == 1,
                  str(body.get("limit")))
            # Si hay mas de 1 evento, truncado debe ser True
            r2 = c.get(
                f"/api/figuras/{SLUG}/grafo/evolucion"
                f"?entidad_a=ollanta-humala&entidad_b=nadine-heredia"
                f"&limit=9999"
            )
            if r2.status_code == 200:
                total_eventos = len(r2.json().get("eventos", []))
                if total_eventos > 1:
                    # Re-pedimos con limit=1: truncado debe ser True
                    check("truncado=True cuando total > limit",
                          body.get("truncado") is True,
                          f"truncado={body.get('truncado')} total={total_eventos}")
        else:
            check("predicado presente (sin eventos, skip)", True)

    print()
    if fallos:
        print(f"FAILED -- {fallos} fallo(s)")
        return 1
    print("OK -- todos los checks pasaron")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
