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

# Créditos de redacción de Andina al final de la nota. NER los toma como
# entidades espurias (NDP/FHG/HTC/JCR…) que contaminan el grafo de actores.
#  - "(FIN)" marca el fin de la nota: todo lo que sigue es crédito.
#  - Variante sin "(FIN)": iniciales en mayúscula + "Publicado: dd/mm/aaaa".
# El 2º patrón EXIGE iniciales en mayúscula justo antes de "Publicado" para no
# borrar texto legítimo como "fue publicado el 1/2/2024".
_CREDITO_FIN = re.compile(r"\(\s*FIN\s*\).*$", re.DOTALL)
_CREDITO_BYLINE = re.compile(
    r"\s*(?:[A-ZÁÉÍÓÚÑ]{2,6}[/\s:]+){1,5}Publicado\s*:?\s*\d{1,2}/\d{1,2}/\d{2,4}.*$",
    re.DOTALL,
)
# Fin de oración: . ! ? (o cierre …) seguido de espacio y mayúscula/comilla/¿¡
_FIN_ORACION = re.compile(r"(?<=[.!?…])\s+(?=[«\"¿¡A-ZÁÉÍÓÚÑ0-9])")

_MIN_CARS = 60   # documentos más cortos se descartan como ruido


def limpiar(texto: str) -> str:
    """Normaliza espacios, quita marcas de cita [1] y créditos de redacción."""
    texto = _CREDITO_FIN.sub("", texto)
    texto = _CREDITO_BYLINE.sub("", texto)
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
    La deduplicación es por FIRMA DE TEXTO, así que funciona CROSS-FUENTE: una
    misma nota republicada por dos medios (distinto `doc_id`/`fuente`, mismo
    cuerpo) se colapsa a una sola. Pasa los documentos de todas las fuentes
    juntos a esta función para que la combinación multi-fuente quede deduplicada.
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
