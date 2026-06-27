"""Tests de resolución de entidades (verdades conocidas, sin red ni modelos).

Valida las piezas de la Fase 2:
  (1) _agrupar: agrupación por contención de tokens (merge de subconjuntos,
      canónico = forma más frecuente, alias preservados).
  (2) _es_actor: filtro por tipo (PER/ORG) y denylist de genéricos.
  (3) descubrir_entidades: filtra ANTES del top_n (con un NER de stub, sin spaCy).
  (4) eval/entities.py: actor_precision/recall, type_accuracy y detección de splits.

Uso:  python scripts/test_entities.py
"""

from __future__ import annotations

from datetime import date

from eval import entities as evalent
import src.pipeline.entity_discovery as ed
from src.pipeline.entity_discovery import (
    _GENERICOS,
    _TIPOS_ACTOR,
    _agrupar,
    _es_actor,
    descubrir_entidades,
)
from src.schemas import Documento, EntidadMencion


def test_agrupar_contencion() -> None:
    menciones = [
        ("Keiko Fujimori", "PER", "d1"),
        ("Keiko Fujimori", "PER", "d2"),
        ("Keiko", "PER", "d3"),
        ("Partido Nacionalista", "ORG", "d1"),
        ("Partido Nacionalista Peruano", "ORG", "d2"),
        ("Pedro Castillo", "PER", "d4"),
    ]
    grupos = _agrupar(menciones)
    por_nombre = {g["nombre"]: g for g in grupos.values()}
    assert len(grupos) == 3, list(por_nombre)
    # "Keiko" se fusiona en "Keiko Fujimori" (forma más frecuente); 3 docs.
    keiko = por_nombre["Keiko Fujimori"]
    assert "Keiko" in keiko["alias"], keiko
    assert keiko["n_docs"] == 3, keiko
    # "Partido Nacionalista Peruano" ⊆ se fusiona; canónico = más corto (empate).
    assert "Partido Nacionalista" in por_nombre, list(por_nombre)
    pn = por_nombre["Partido Nacionalista"]
    assert "Partido Nacionalista Peruano" in pn["alias"], pn
    print("  OK _agrupar: contención fusiona subconjuntos, canónico por frecuencia")


def test_es_actor() -> None:
    assert _es_actor({"tipo": "PER", "nombre": "Keiko Fujimori"}, _TIPOS_ACTOR, _GENERICOS)
    assert _es_actor({"tipo": "ORG", "nombre": "Fuerza Popular"}, _TIPOS_ACTOR, _GENERICOS)
    assert not _es_actor({"tipo": "LOC", "nombre": "Lima"}, _TIPOS_ACTOR, _GENERICOS)
    assert not _es_actor({"tipo": "MISC", "nombre": "Ley"}, _TIPOS_ACTOR, _GENERICOS)
    # Genérico aunque sea ORG ("Estado").
    assert not _es_actor({"tipo": "ORG", "nombre": "Estado"}, _TIPOS_ACTOR, _GENERICOS)
    print("  OK _es_actor: retiene PER/ORG, descarta LOC/MISC y genéricos")


def test_descubrir_filtra() -> None:
    docs = [
        Documento(doc_id=f"andina:{i}", fuente="andina.pe", url="u",
                  fecha_pub=date(2021, 1, 1), texto=f"texto {i}")
        for i in range(3)
    ]
    menciones_por_doc = [
        [EntidadMencion(texto="Keiko Fujimori", tipo="PER", inicio=0, fin=1),
         EntidadMencion(texto="Lima", tipo="LOC", inicio=2, fin=3)],
        [EntidadMencion(texto="Keiko Fujimori", tipo="PER", inicio=0, fin=1),
         EntidadMencion(texto="Fuerza Popular", tipo="ORG", inicio=2, fin=3)],
        [EntidadMencion(texto="Estado", tipo="ORG", inicio=0, fin=1),
         EntidadMencion(texto="Pedro Castillo", tipo="PER", inicio=2, fin=3)],
    ]

    original = ed.get_ner_model
    ed.get_ner_model = lambda: (lambda textos: menciones_por_doc)
    try:
        nodos = descubrir_entidades(docs, top_n=10, enriquecer_wikidata=False)
    finally:
        ed.get_ner_model = original

    nombres = [n.nombre for n in nodos]
    assert set(nombres) == {"Keiko Fujimori", "Fuerza Popular", "Pedro Castillo"}, nombres
    assert "Lima" not in nombres and "Estado" not in nombres, nombres
    # Ranking: Keiko (2 docs × PER) primero.
    assert nodos[0].nombre == "Keiko Fujimori", nombres
    print("  OK descubrir_entidades: filtra LOC/genéricos, rankea, top_n tras filtrar")


def test_eval_entidades() -> None:
    filas = [
        {"nombre": "Keiko Fujimori", "tipo": "PER", "retenida": "1",
         "es_actor_gold": "1", "tipo_correcto": "PER", "nombre_canonico": "Keiko Fujimori"},
        {"nombre": "Lima", "tipo": "LOC", "retenida": "0",
         "es_actor_gold": "0", "tipo_correcto": "LOC", "nombre_canonico": ""},
        {"nombre": "Estado", "tipo": "ORG", "retenida": "0",
         "es_actor_gold": "0", "tipo_correcto": "", "nombre_canonico": ""},
        {"nombre": "Keiko", "tipo": "PER", "retenida": "1",
         "es_actor_gold": "1", "tipo_correcto": "PER", "nombre_canonico": "Keiko Fujimori"},
        {"nombre": "Fuerza Popular", "tipo": "PER", "retenida": "1",
         "es_actor_gold": "1", "tipo_correcto": "ORG", "nombre_canonico": "Fuerza Popular"},
    ]
    m = evalent.evaluar(filas)
    assert abs(m["actor_precision"] - 1.0) < 1e-9, m
    assert abs(m["actor_recall"] - 1.0) < 1e-9, m
    assert abs(m["type_accuracy"] - 0.75) < 1e-9, m   # Fuerza Popular: PER vs ORG
    assert m["splits"] == {"Keiko Fujimori": 2}, m     # "Keiko" + "Keiko Fujimori"
    print("  OK eval/entities: precision/recall/type_accuracy/splits correctos")


def main() -> None:
    print("== (1) _agrupar (contención de tokens) ==")
    test_agrupar_contencion()
    print("\n== (2) _es_actor (filtro tipo + genéricos) ==")
    test_es_actor()
    print("\n== (3) descubrir_entidades (filtra antes del top_n, NER stub) ==")
    test_descubrir_filtra()
    print("\n== (4) eval/entities (métricas) ==")
    test_eval_entidades()
    print("\n[OK] TODOS LOS TESTS DE RESOLUCIÓN DE ENTIDADES PASARON")


if __name__ == "__main__":
    main()
