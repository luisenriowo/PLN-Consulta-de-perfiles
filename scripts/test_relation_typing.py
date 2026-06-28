"""Tests offline del tipado inducido de relaciones abiertas.

No carga SentenceTransformer: inyecta vectores pequeños y usa DuckDB temporal.
Uso:  python scripts/test_relation_typing.py
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import numpy as np

_TMP = Path(tempfile.mkdtemp(prefix="test_reltyping_"))
os.environ["TIMELINE_DATA_DIR"] = str(_TMP)

from eval import openie as eval_openie  # noqa: E402
from eval import relation_typing as eval_typing  # noqa: E402
from src.pipeline.relation_typing import (  # noqa: E402
    PredicateInstance,
    aplicar_etiquetas,
    asignaciones,
    cargar_predicados,
    clusterizar_predicados,
)
from src.schemas import EntityNode, RelationEdge  # noqa: E402
from src.storage import KnowledgeGraph  # noqa: E402


def _inst(relation_id: int, predicado: str) -> PredicateInstance:
    return PredicateInstance(
        relation_id=relation_id,
        predicado=predicado,
        origen_id="e1",
        destino_id="e2",
        origen_nombre="Alpha",
        destino_nombre="Beta",
        fecha=date(2024, 1, relation_id),
        evidencia=[f"Alpha {predicado} Beta."],
    )


def test_clusterizar_predicados() -> None:
    instancias = [
        _inst(1, "acusar"),
        _inst(2, "denunciar"),
        _inst(3, "apoyar"),
        _inst(4, "respaldar"),
    ]
    vectores = np.array(
        [
            [1.0, 0.0],
            [0.98, 0.02],
            [0.0, 1.0],
            [0.02, 0.98],
        ]
    )
    clusters = clusterizar_predicados(
        instancias, distance_threshold=0.05, vectores=vectores
    )
    grupos = [sorted(i.relation_id for i in c.instances) for c in clusters]
    assert sorted(grupos) == [[1, 2], [3, 4]], grupos
    rows = asignaciones(clusters)
    assert [r["relation_id"] for r in rows] == [1, 2, 3, 4], rows
    print("  OK clustering inducido: 4 predicados -> 2 clusters")


def test_aplicar_etiquetas() -> None:
    slug = "tipado_tmp"
    with KnowledgeGraph(slug) as grafo:
        grafo.upsert_entity(EntityNode(entity_id="e1", nombre="Alpha", tipo="PER"))
        grafo.upsert_entity(EntityNode(entity_id="e2", nombre="Beta", tipo="ORG"))
        rid1 = grafo.insert_relation(
            RelationEdge(
                origen_id="e1",
                destino_id="e2",
                predicado="acusar",
                tipo=None,
                fecha=date(2024, 1, 1),
                evidencia=["Alpha acusó a Beta."],
                fuentes=["andina:1"],
                confianza=1.0,
                metodo="openie",
            )
        )
        rid2 = grafo.insert_relation(
            RelationEdge(
                origen_id="e1",
                destino_id="e2",
                predicado="apoyar",
                tipo=None,
                fecha=date(2024, 1, 2),
                evidencia=["Alpha apoyó a Beta."],
                fuentes=["andina:2"],
                confianza=1.0,
                metodo="openie",
            )
        )
        instancias = cargar_predicados(grafo)
        assert len(instancias) == 2, instancias
        n = aplicar_etiquetas(
            grafo,
            [
                {"relation_id": rid1, "cluster_id": "reltype:000"},
                {"relation_id": rid2, "cluster_id": "reltype:001"},
            ],
            {"reltype:000": "acusacion", "reltype:001": "alianza"},
        )
        assert n == 2, n
    with KnowledgeGraph(slug, read_only=True) as grafo:
        tipos = {int(r["id"]): r["tipo"] for r in grafo.relations()}
    assert tipos[rid1] == "acusacion", tipos
    assert tipos[rid2] == "alianza", tipos
    print("  OK aplicar etiquetas: relations.tipo actualizado")


def test_eval_openie_y_tipado() -> None:
    csv_path = _TMP / "gold_openie.csv"
    csv_path.write_text(
        "relation_id,cluster_id,tipo_sugerido,tipo_gold,triple_valido_gold,predicado_ok_gold\n"
        "1,reltype:000,acusacion,acusacion,1,1\n"
        "2,reltype:000,acusacion,conflicto,1,0\n"
        "3,reltype:001,alianza,alianza,0,1\n",
        encoding="utf-8",
    )
    m_openie = eval_openie.evaluar(str(csv_path))
    assert abs(m_openie["precision_triple"] - (2 / 3)) < 1e-9, m_openie
    assert abs(m_openie["precision_predicado"] - (2 / 3)) < 1e-9, m_openie
    m_tipo = eval_typing.evaluar(str(csv_path))
    assert abs(m_tipo["accuracy"] - (2 / 3)) < 1e-9, m_tipo
    assert m_tipo["coherencia_clusters"]["n_clusters"] == 2, m_tipo
    print("  OK eval: OpenIE y tipado computan métricas esperadas")


def main() -> None:
    print("== (1) Clustering inducido ==")
    test_clusterizar_predicados()
    print("\n== (2) Persistencia en grafo ==")
    test_aplicar_etiquetas()
    print("\n== (3) Evaluación ==")
    test_eval_openie_y_tipado()
    print("\n[OK] TODOS LOS TESTS DE TIPADO INDUCIDO PASARON")


if __name__ == "__main__":
    main()
