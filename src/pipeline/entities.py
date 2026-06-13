"""Backbone — NER + entity linking (FIJO, compartido por las 4 condiciones).

Reconoce entidades con spaCy (es_core_news_lg en producción) y resuelve las
menciones de la familia Humala a una entidad canónica vía gazetteer. Esta
desambiguación (Ollanta / Antauro / Isaac Humala / Nadine Heredia) es la que
 §3 exige explícitamente.

Las menciones detectadas se adjuntan a `Documento.entidades`. No depende del
sujeto: el gazetteer es de dominio (la familia y orgs asociadas), no del query.
"""

from __future__ import annotations

import functools
import unicodedata

import spacy

from src.schemas import Documento, EntidadMencion

MODELO_DEFECTO = "es_core_news_lg"  #  §4; el smoke usa es_core_news_md

# Gazetteer de dominio: forma de superficie (normalizada) -> (id, nombre canónico).
# La normalización quita acentos y pasa a minúsculas (ver `_norm`).
_GAZETTEER: dict[str, tuple[str, str]] = {
    "ollanta humala": ("humala:ollanta", "Ollanta Humala"),
    "ollanta humala tasso": ("humala:ollanta", "Ollanta Humala"),
    "ollanta moises humala tasso": ("humala:ollanta", "Ollanta Humala"),
    "ollanta": ("humala:ollanta", "Ollanta Humala"),
    "antauro humala": ("humala:antauro", "Antauro Humala"),
    "antauro": ("humala:antauro", "Antauro Humala"),
    "isaac humala": ("humala:isaac", "Isaac Humala"),
    "nadine heredia": ("heredia:nadine", "Nadine Heredia"),
    "nadine heredia alarcon": ("heredia:nadine", "Nadine Heredia"),
    "nadine": ("heredia:nadine", "Nadine Heredia"),
    "partido nacionalista peruano": (
        "org:partido-nacionalista",
        "Partido Nacionalista Peruano",
    ),
    "partido nacionalista": (
        "org:partido-nacionalista",
        "Partido Nacionalista Peruano",
    ),
}

# Etiquetas de entidad que conservamos (modelos es_core_news_*).
_TIPOS = {"PER", "ORG", "LOC", "MISC"}


def _norm(texto: str) -> str:
    """Minúsculas sin acentos ni puntuación de borde, para casar el gazetteer."""
    sin_acentos = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return sin_acentos.lower().strip(" .,;:«»\"'()").strip()


def _canonicalizar(superficie: str, tipo: str) -> tuple[str | None, str | None]:
    """Resuelve una mención a (id, nombre) canónicos; (None, None) si no enlaza.

    Reglas, en orden:
      1. Coincidencia exacta en el gazetteer.
      2. Si la mención contiene un nombre de pila distintivo de la familia
         (antauro/isaac/nadine), gana ese.
      3. 'Humala' a secas → Ollanta (sujeto por defecto del caso). Heurística
         documentada: en un corpus centrado en el expresidente, el apellido
         solo suele referirlo a él.
    """
    n = _norm(superficie)
    if n in _GAZETTEER:
        return _GAZETTEER[n]
    if tipo == "PER":
        if "antauro" in n:
            return _GAZETTEER["antauro"]
        if "isaac" in n:
            return _GAZETTEER["isaac humala"]
        if "nadine" in n or "heredia" in n:
            return _GAZETTEER["nadine"]
        if "humala" in n:
            return _GAZETTEER["ollanta"]
    return None, None


@functools.lru_cache(maxsize=2)
def cargar_modelo(nombre: str = MODELO_DEFECTO):
    """Carga (y cachea) el modelo spaCy. Solo NER: desactiva lo innecesario."""
    return spacy.load(nombre, disable=["lemmatizer", "morphologizer", "tagger"])


def link_entities(
    docs: list[Documento], *, modelo: str = MODELO_DEFECTO
) -> list[Documento]:
    """Detecta entidades y resuelve menciones de la familia Humala.

    Devuelve documentos nuevos con `entidades` rellenado; no muta la entrada.
    """
    nlp = cargar_modelo(modelo)
    salida: list[Documento] = []
    for doc, spacy_doc in zip(docs, nlp.pipe(d.texto for d in docs)):
        menciones: list[EntidadMencion] = []
        for ent in spacy_doc.ents:
            if ent.label_ not in _TIPOS:
                continue
            ent_id, ent_nombre = _canonicalizar(ent.text, ent.label_)
            menciones.append(
                EntidadMencion(
                    texto=ent.text,
                    tipo=ent.label_,
                    inicio=ent.start_char,
                    fin=ent.end_char,
                    entidad_id=ent_id,
                    entidad_nombre=ent_nombre,
                )
            )
        salida.append(doc.model_copy(update={"entidades": menciones}))
    return salida
