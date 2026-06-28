"""Tests del pipeline de relaciones (verdades conocidas, sin gold ni red).

Valida, ANTES de tener el gold humano real, las piezas de la Fase 1:
  (1) RuleBasedClassifier: oraciones con tipo conocido → tipo esperado.
  (2) Arnés eval/relations.py: P/R/F1, accuracy y matriz de confusión sobre un
      fixture de predicciones conocidas (aísla la AGREGACIÓN de la métrica).
  (3) HybridClassifier con umbral=0.0 nunca escala al LLM (queda en reglas).
  (4) KnowledgeGraph: roundtrip entidad + relación en una BD temporal.
  (5) cargar_gold: parseo del CSV de gold (filas sin etiquetar se omiten).

No requiere API key, red ni modelos spaCy (el clasificador de reglas opera sobre
la oración cuando no hay dep-triple).

Uso:  python scripts/test_relations.py
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

# graph.py fija su directorio de datos al IMPORTARSE; apuntarlo a un temporal
# ANTES de importar src.storage para no tocar data/ real.
_TMP = Path(tempfile.mkdtemp(prefix="test_rel_"))
os.environ["TIMELINE_DATA_DIR"] = str(_TMP)

from eval import relations as evalrel  # noqa: E402
from src.pipeline.relation_classifier import (  # noqa: E402
    HybridClassifier,
    RuleBasedClassifier,
)
from src.pipeline.relations import Coocurrencia  # noqa: E402
from src.schemas import EntityNode, RelationEdge  # noqa: E402
from src.storage import KnowledgeGraph  # noqa: E402


def _cooc(
    oracion: str, *, verbo: str | None = None, a: str = "A", b: str = "B"
) -> Coocurrencia:
    triple = ("", verbo, "") if verbo else None
    return Coocurrencia(
        entity_a=EntityNode(entity_id=a, nombre=a, tipo="PER"),
        entity_b=EntityNode(entity_id=b, nombre=b, tipo="PER"),
        oracion=oracion,
        doc_id="d",
        fecha=date(2021, 1, 1),
        triple=triple,
    )


def test_reglas() -> None:
    clf = RuleBasedClassifier()
    casos = [
        ("El presidente nombró a Pedro como ministro.", "nombramiento"),
        ("La fiscalía acusó a Keiko por lavado de activos.", "acusacion"),
        ("Pedro renunció al partido tras la disputa.", "ruptura"),
        ("Pedro pertenece al partido Perú Libre.", "pertenencia"),
        ("El congresista apoyó a su aliado en el pleno.", "alianza"),
        ("La bancada rechazó la propuesta del Ejecutivo.", "conflicto"),
        ("Ambos asistieron a la ceremonia en Lima.", "mencion"),
    ]
    for oracion, esperado in casos:
        got = clf.classify(_cooc(oracion)).tipo
        assert got == esperado, f"{oracion!r} -> {got} (esperado {esperado})"
    print("  OK reglas:", [c[1] for c in casos])


def test_harness() -> None:
    # 4 ejemplos; el 4º tiene gold=nombramiento pero reglas dirá 'mencion' → 1 error.
    ejemplos = [
        (_cooc("El presidente nombró a X ministro."), "nombramiento"),
        (_cooc("La fiscalía acusó a Y por corrupción."), "acusacion"),
        (_cooc("Z renunció a su cargo."), "ruptura"),
        (_cooc("Ambos viajaron juntos al sur."), "nombramiento"),
    ]
    m = evalrel.evaluar(RuleBasedClassifier(), ejemplos)
    assert m["n"] == 4, m
    assert abs(m["accuracy"] - 0.75) < 1e-9, m["accuracy"]
    # nombramiento: 2 gold, 1 acertado → recall 0.5, precision 1.0
    assert m["por_tipo"]["nombramiento"]["support"] == 2, m["por_tipo"]["nombramiento"]
    assert abs(m["por_tipo"]["nombramiento"]["recall"] - 0.5) < 1e-9, m["por_tipo"][
        "nombramiento"
    ]
    assert abs(m["por_tipo"]["nombramiento"]["precision"] - 1.0) < 1e-9, m["por_tipo"][
        "nombramiento"
    ]
    assert m["confusion"][("nombramiento", "mencion")] == 1, m["confusion"]
    print(
        f"  OK arnés: accuracy={m['accuracy']:.2f}, recall(nombramiento)=0.50, confusión correcta"
    )


def test_hibrido_umbral0() -> None:
    # umbral=0.0: incluso una 'mencion' (confianza 0.40) supera el umbral → reglas.
    r = HybridClassifier(umbral=0.0).classify(_cooc("Ambos asistieron a un acto."))
    assert r.metodo == "rules", r
    print("  OK híbrido umbral=0.0 no escala al LLM (metodo=rules)")


def test_calibrated_routing() -> None:
    from src.pipeline.relation_classifier import CalibratedClassifier

    clf = CalibratedClassifier()
    clf._llm_desactivado = True  # fuerza fallback a reglas (sin red)
    # 'mencion' → reglas (no llama al LLM)
    r1 = clf.classify(_cooc("Ambos asistieron a la ceremonia en Lima."))
    assert r1.tipo == "mencion" and r1.metodo == "rules", r1
    # tipada → enruta al LLM; con LLM desactivado cae a reglas sin crashear
    r2 = clf.classify(_cooc("La fiscalía acusó a X por corrupción."))
    assert r2.tipo == "acusacion" and r2.metodo == "rules", r2
    # classify_grupo: grupo todo-mencion → mencion
    g = clf.classify_grupo(
        [_cooc("Ambos viajaron al sur."), _cooc("Se vieron en Lima.")]
    )
    assert g.tipo == "mencion", g
    print("  OK CalibratedClassifier: mencion por reglas, tipada enruta al LLM")


def test_grafo_roundtrip() -> None:
    slug = "test_tmp"
    with KnowledgeGraph(slug) as g:
        g.upsert_entity(EntityNode(entity_id="e1", nombre="Alpha", tipo="PER"))
        g.upsert_entity(EntityNode(entity_id="e2", nombre="Beta", tipo="ORG"))
        rid = g.insert_relation(
            RelationEdge(
                origen_id="e1",
                destino_id="e2",
                tipo="alianza",
                fecha=date(2022, 5, 1),
                evidencia=["Alpha apoyó a Beta."],
                fuentes=["andina:1"],
                confianza=0.8,
                metodo="rules",
            )
        )
        assert isinstance(rid, int), rid
        rid_open = g.insert_relation(
            RelationEdge(
                origen_id="e1",
                destino_id="e2",
                tipo=None,
                predicado="acusar por",
                fecha=date(2022, 5, 2),
                evidencia=["Alpha fue acusado por Beta."],
                fuentes=["andina:2"],
                confianza=1.0,
                metodo="openie",
            )
        )
        assert isinstance(rid_open, int), rid_open
    with KnowledgeGraph(slug, read_only=True) as g:
        ents, rels = g.entities(), g.relations()
        assert len(ents) == 2, ents
        assert len(rels) == 2, rels
        assert rels[0]["tipo"] == "alianza", rels[0]
        assert rels[0]["origen_nombre"] == "Alpha", rels[0]
        assert rels[0]["destino_nombre"] == "Beta", rels[0]
        assert rels[1]["tipo"] is None and rels[1]["predicado"] == "acusar por", rels[1]
    print("  OK grafo roundtrip: 2 entidades, relación tipada y relación abierta")


def test_cargar_gold() -> None:
    csv_txt = (
        "entity_a,entity_b,oracion,doc_id,fecha,"
        "triple_sujeto,triple_verbo,triple_objeto,tipo_sugerido,tipo_gold\n"
        "Castillo,Cerrón,Castillo nombró a Cerrón,andina:1,2021-07-01,,nombrar,,nombramiento,nombramiento\n"
        "Keiko,JNE,La fiscalía acusó a Keiko,andina:2,2022-03-01,,acusar,,acusacion,\n"  # sin etiqueta → se omite
    )
    ruta = _TMP / "fixture_gold.csv"
    ruta.write_text(csv_txt, encoding="utf-8")
    ejemplos = evalrel.cargar_gold(ruta)
    assert len(ejemplos) == 1, ejemplos  # solo la fila etiquetada
    cooc, tipo = ejemplos[0]
    assert tipo == "nombramiento", tipo
    assert cooc.triple == ("", "nombrar", ""), cooc.triple
    print("  OK cargar_gold: omite filas sin etiquetar, reconstruye el triple")


def main() -> None:
    print("== (1) RuleBasedClassifier (tipos conocidos) ==")
    test_reglas()
    print("\n== (2) Arnés eval/relations (P/R/F1, confusión) ==")
    test_harness()
    print("\n== (3) HybridClassifier umbral=0.0 (sin LLM) ==")
    test_hibrido_umbral0()
    print("\n== (3b) CalibratedClassifier (enrutamiento por tipo) ==")
    test_calibrated_routing()
    print("\n== (4) KnowledgeGraph roundtrip ==")
    test_grafo_roundtrip()
    print("\n== (5) cargar_gold (parseo CSV) ==")
    test_cargar_gold()
    print("\n[OK] TODOS LOS TESTS DEL PIPELINE DE RELACIONES PASARON")


if __name__ == "__main__":
    main()
