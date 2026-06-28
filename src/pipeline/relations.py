"""Backbone — Extracción de co-ocurrencias y candidatos de relación.

Primera etapa del pipeline de relaciones: dado el corpus y la lista de
entidades descubiertas, encuentra las oraciones donde dos entidades
co-aparecen. Para cada par extrae, vía dependency parsing, el triple
superficial (sujeto, verbo_raíz, objeto) que luego usa el clasificador.

La clasificación del TIPO de relación no ocurre aquí; es responsabilidad
de RelationClassifier (relation_classifier.py). Separar detección de
clasificación mantiene esta etapa libre de dependencias al LLM y permite
testearla de forma aislada.

Co-ocurrencia ≠ relación: dos entidades co-aparecen cuando están en la
misma oración. El clasificador decide después si hay relación semántica
real y de qué tipo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Iterator

from src.pipeline._utils import _norm
from src.schemas import Documento, EntityNode

# Separa oraciones en puntuación de cierre + espacio.
_RE_SEP_ORACION = re.compile(r"(?<=[.!?])\s+")
# Longitud mínima de una oración para considerarla candidata.
_MIN_CHARS = 15


# ── Estructura de datos ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Coocurrencia:
    """Par de entidades que co-aparecen en una oración con su contexto.

    `triple` es (sujeto, verbo_lema, objeto) del dep parse superficial.
    Es None cuando el dep parse no encuentra estructura sujeto-verbo-objeto
    clara (p. ej. oraciones nominales o muy fragmentadas).
    """

    entity_a: EntityNode
    entity_b: EntityNode
    oracion: str
    doc_id: str
    fecha: date
    triple: tuple[str, str, str] | None = field(default=None, compare=False)


# ── Helpers internos ───────────────────────────────────────────────────────


def _segmentar(texto: str) -> list[str]:
    """Divide el texto en oraciones por puntuación de cierre."""
    return [
        s.strip() for s in _RE_SEP_ORACION.split(texto) if len(s.strip()) >= _MIN_CHARS
    ]


@lru_cache(maxsize=8192)
def _patron_palabra(texto_norm: str) -> re.Pattern:
    """Patrón con límite de palabra para `texto_norm` (cacheado por forma)."""
    return re.compile(r"\b" + re.escape(texto_norm) + r"\b")


def _contiene(oracion_norm: str, forma: str) -> bool:
    """True si `forma` aparece como PALABRA en la oración (no como substring).

    Pre-filtra con `in` (rápido) y confirma con límite de palabra: evita que
    nombres cortos ("Ma", "Pro") casen dentro de otras palabras ("Lima",
    "programa") y exploten el grafo con co-ocurrencias falsas.
    """
    return forma in oracion_norm and bool(_patron_palabra(forma).search(oracion_norm))


def _menciona(oracion_norm: str, node: EntityNode) -> bool:
    """True si la oración menciona (como palabra) el nombre canónico o un alias.

    Los alias vienen de entity_discovery: todas las formas superficiales que
    aparecieron en el corpus para este nodo. Se aplica un mínimo de 6 chars a los
    alias para evitar falsos positivos con formas muy cortas.
    """
    if _contiene(oracion_norm, _norm(node.nombre)):
        return True
    for a in node.alias:
        a_norm = _norm(a)
        if len(a_norm) >= 6 and _contiene(oracion_norm, a_norm):
            return True
    return False


def _dep_triple(oracion: str, nlp) -> tuple[str, str, str] | None:
    """Extrae el triple dominante (sujeto, verbo_raíz_lema, objeto) via dep.

    Retorna None si no hay verbo raíz con sujeto u objeto identificables;
    esto ocurre en titulares nominales o fragmentos sin verbo principal.
    """
    doc = nlp(oracion)
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root is None or root.pos_ not in {"VERB", "AUX"}:
        return None

    sujeto = next((t.text for t in root.lefts if t.dep_ in {"nsubj", "nsubjpass"}), "")
    objeto = next((t.text for t in root.rights if t.dep_ in {"obj", "dobj", "obl"}), "")
    if not sujeto and not objeto:
        return None
    return (sujeto, root.lemma_, objeto)


def _token_entidad(doc, nombre: str):
    """Primer token del doc cuya forma coincide con una palabra del nombre."""
    palabras = {p for p in _norm(nombre).split() if len(p) > 2}
    for t in doc:
        if _norm(t.text) in palabras:
            return t
    return None


def _camino_dep(a, b) -> list:
    """Camino en el árbol de dependencias entre dos tokens (vía ancestro común)."""
    anc_a = [a] + list(a.ancestors)
    idx_b = {t.i: k for k, t in enumerate([b] + list(b.ancestors))}
    lca = next((t for t in anc_a if t.i in idx_b), None)
    if lca is None:
        return []
    rama_a = []
    for t in anc_a:
        rama_a.append(t)
        if t.i == lca.i:
            break
    rama_b = []
    for t in [b] + list(b.ancestors):
        if t.i == lca.i:
            break
        rama_b.append(t)
    return rama_a + list(reversed(rama_b))


def relacion_abierta(oracion: str, ent_a: str, ent_b: str, nlp) -> str | None:
    """Frase-predicado LIBRE que conecta a `ent_a` y `ent_b` en la oración.

    OpenIE-lite: ubica un token de cada entidad, toma el camino de dependencias
    entre ambos y devuelve una frase verbal corta (p. ej. "nombrar", "acusar
    por", "se enfrentar con"). No impone taxonomía: el TIPO se identifica
    después (agrupando predicados o con LLM on-demand). Si no hay verbo útil en
    el camino, cae al verbo raíz; None si solo encuentra verbos de reporte.
    """
    return _predicado(nlp(oracion), ent_a, ent_b)


def _predicado(doc, ent_a: str, ent_b: str) -> str | None:
    """Predicado conector entre dos entidades sobre un doc YA parseado."""
    ta, tb = _token_entidad(doc, ent_a), _token_entidad(doc, ent_b)
    if ta is not None and tb is not None:
        for verbo in [t for t in _camino_dep(ta, tb) if t.pos_ in {"VERB", "AUX"}]:
            pred = _frase_predicado(verbo)
            if pred:
                return pred
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    if root and root.pos_ in {"VERB", "AUX"}:
        pred = _frase_predicado(root)
        if pred:
            return pred
    # Precision-first: NO se cae a "cualquier verbo de la oración". Si ningún
    # verbo CONECTA a las dos entidades (camino) ni es la acción principal (raíz),
    # no hay relación entre ELLAS → None (co-ocurrencia ≠ relación).
    return None


_VERBOS_REPORTE = {
    "afirmar",
    "agregar",
    "anunciar",
    "asegurar",
    "comentar",
    "contar",
    "declarar",
    "decir",
    "detallar",
    "explicar",
    "indicar",
    "informar",
    "manifestar",
    "mencionar",
    "precisar",
    "referir",
    "responder",
    "senalar",
    "sostener",
    "subrayar",
}

# Verbos NO relacionales: copulativos, auxiliares, modales, "ligeros" y de
# navegación. Dominan el camino de dependencias pero no expresan una relación
# entre las entidades (ser/estar/haber/tener/poder/deber; "Lee también" → leer).
_VERBOS_VACIOS = {
    "ser", "estar", "haber", "tener", "poder", "deber", "hacer", "ir",
    "querer", "saber", "leer", "recordar", "ver", "dar", "quedar",
    "destacar", "resaltar", "remarcar",
}


def _lemma(token) -> str:
    """Lema estable; cae a texto normalizado si spaCy no trae lematizador."""
    lema = (getattr(token, "lemma_", "") or "").strip().lower()
    if not lema or lema == "-pron-":
        lema = token.text.lower()
    return _norm(lema)


def _frase_predicado(verbo) -> str | None:
    """Normaliza verbo conector y añade preposición informativa si existe."""
    lema = _lemma(verbo)
    if not lema or lema in _VERBOS_REPORTE or lema in _VERBOS_VACIOS:
        return None

    partes: list[str] = []
    if any(_norm(h.text) == "se" and h.i < verbo.i for h in verbo.children):
        partes.append("se")
    partes.append(lema)

    prep = _prep_del_verbo(verbo)
    if prep:
        partes.append(prep)
    return " ".join(partes)


def _prep_del_verbo(verbo) -> str | None:
    """Preposición asociada al complemento verbal: acusar por, renunciar a."""
    for child in sorted(verbo.children, key=lambda t: t.i):
        if child.dep_ in {"case", "mark"} and child.pos_ == "ADP":
            return _norm(child.text)
        if child.dep_ in {"obl", "obj", "iobj", "nmod"}:
            for nieto in sorted(child.children, key=lambda t: t.i):
                if nieto.dep_ == "case" and nieto.pos_ == "ADP":
                    return _norm(nieto.text)
    return None


@lru_cache(maxsize=1)
def _nlp_dep():
    """Carga spaCy con solo el dep parser (sin NER, más rápido).

    Modelo configurable via SPACY_DEP_MODEL (default: es_core_news_lg).
    """
    import spacy

    model = os.environ.get("SPACY_DEP_MODEL", "es_core_news_lg")
    return spacy.load(model, disable=["ner"])


# ── API pública ────────────────────────────────────────────────────────────


def extraer_coocurrencias(
    docs: list[Documento],
    entidades: list[EntityNode],
    *,
    min_entidades: int = 2,
) -> Iterator[Coocurrencia]:
    """Genera co-ocurrencias de entidades en oraciones compartidas.

    Generador: procesa un documento a la vez y hace yield de cada par,
    sin acumular la lista completa en memoria.

    Args:
        docs:          Corpus de documentos a analizar.
        entidades:     Lista de EntityNode descubiertas por entity_discovery.
        min_entidades: Mínimo de entidades distintas por oración (default 2).

    Yields:
        Coocurrencia por cada par de entidades en la misma oración.
        El orden refleja el orden cronológico del corpus.
    """
    nlp = _nlp_dep()

    for doc in docs:
        for oracion in _segmentar(doc.texto):
            oracion_norm = _norm(oracion)
            presentes = [e for e in entidades if _menciona(oracion_norm, e)]

            if len(presentes) < min_entidades:
                continue

            triple = _dep_triple(oracion, nlp)

            for i, ea in enumerate(presentes):
                for eb in presentes[i + 1 :]:
                    yield Coocurrencia(
                        entity_a=ea,
                        entity_b=eb,
                        oracion=oracion,
                        doc_id=doc.doc_id,
                        fecha=doc.fecha_pub,
                        triple=triple,
                    )


@dataclass(frozen=True)
class RelacionAbierta:
    """Relación ABIERTA fechada entre dos entidades (OpenIE).

    `predicado` es el verbo conector libre (sin taxonomía); el TIPO se identifica
    después. La `fecha` la hace una arista TEMPORAL: el mismo par puede tener
    varias a lo largo del tiempo → permite ver cómo evoluciona la relación.
    """

    entity_a: EntityNode
    entity_b: EntityNode
    predicado: str
    oracion: str
    doc_id: str
    fecha: date


def extraer_relaciones_abiertas(
    docs: list[Documento],
    entidades: list[EntityNode],
    *,
    min_entidades: int = 2,
    max_entidades: int = 6,
) -> Iterator[RelacionAbierta]:
    """Genera relaciones ABIERTAS fechadas (una por par co-ocurrente con verbo).

    A diferencia de `extraer_coocurrencias` + clasificación + colapso por par,
    aquí NO se agrega: cada co-ocurrencia con predicado válido es una arista
    temporal independiente. Así el grafo es un multigrafo en el tiempo y se puede
    reconstruir la evolución de cualquier par. Parsea cada oración UNA vez.

    `max_entidades`: salta oraciones con demasiadas entidades (listas de
    gabinete/candidatos, bancadas). Son enumeraciones, no relaciones par-a-par,
    y su combinatoria (C(n,2)) hace explotar el grafo con ruido `mencion`.
    """
    nlp = _nlp_dep()
    for doc in docs:
        for oracion in _segmentar(doc.texto):
            oracion_norm = _norm(oracion)
            presentes = [e for e in entidades if _menciona(oracion_norm, e)]
            if not (min_entidades <= len(presentes) <= max_entidades):
                continue
            parsed = nlp(oracion)
            for i, ea in enumerate(presentes):
                for eb in presentes[i + 1 :]:
                    pred = _predicado(parsed, ea.nombre, eb.nombre)
                    if pred:
                        yield RelacionAbierta(
                            entity_a=ea,
                            entity_b=eb,
                            predicado=pred,
                            oracion=oracion,
                            doc_id=doc.doc_id,
                            fecha=doc.fecha_pub,
                        )
