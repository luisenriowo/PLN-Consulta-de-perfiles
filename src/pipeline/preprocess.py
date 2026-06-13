"""Backbone — Preprocesamiento (FIJO, compartido por las 4 condiciones).

Limpieza, segmentación en oraciones y deduplicación de documentos. Devuelve
`list[Documento]` ya limpia y sin duplicados; es idéntico para todas las
condiciones (no debe introducir sesgos aguas arriba del punto de swap).

No depende de NER: la segmentación es un splitter ligero por reglas, para que
el preproceso sea independiente de spaCy.
"""

from __future__ import annotations

import re

from src.schemas import Documento

_CORCHETES = re.compile(r"\[\s*(?:\d+|cita\s+requerida|sin fuentes?)\s*\]", re.IGNORECASE)
_ESPACIOS = re.compile(r"[ \t ]+")
_SALTOS = re.compile(r"\n{2,}")
# Fin de oración: . ! ? (o cierre …) seguido de espacio y mayúscula/comilla/¿¡
_FIN_ORACION = re.compile(r"(?<=[.!?…])\s+(?=[«\"¿¡A-ZÁÉÍÓÚÑ0-9])")

_MIN_CARS = 60   # documentos más cortos se descartan como ruido


def limpiar(texto: str) -> str:
    """Normaliza espacios y quita marcas de cita tipo [1] / [cita requerida]."""
    texto = _CORCHETES.sub("", texto)
    texto = _ESPACIOS.sub(" ", texto)
    texto = _SALTOS.sub("\n", texto)
    return texto.strip()


def segmentar_oraciones(texto: str) -> list[str]:
    """Segmenta en oraciones con un splitter por reglas (es)."""
    texto = texto.replace("\n", " ").strip()
    if not texto:
        return []
    return [o.strip() for o in _FIN_ORACION.split(texto) if o.strip()]


def _firma(texto: str) -> str:
    """Firma normalizada para detectar duplicados (minúsculas, solo alfanum)."""
    return re.sub(r"[^a-z0-9áéíóúñ]+", "", texto.lower())


def preprocess(docs: list[Documento]) -> list[Documento]:
    """Limpia, descarta ruido corto y deduplica documentos.

    El orden de entrada se preserva; ante duplicados gana la primera aparición.
    """
    vistos: set[str] = set()
    salida: list[Documento] = []
    for doc in docs:
        texto = limpiar(doc.texto)
        if len(texto) < _MIN_CARS:
            continue
        firma = _firma(texto)
        if firma in vistos:
            continue
        vistos.add(firma)
        salida.append(doc.model_copy(update={"texto": texto}))
    return salida
