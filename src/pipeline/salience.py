"""Backbone — Selección de saliencia (FIJO, compartido por las 4 condiciones).

Selecciona los `EventCluster` salientes que entran a la línea de tiempo. Es la
última etapa antes del punto de swap: su salida es idéntica para las 4
condiciones, así que NO debe sesgar la comparación.

Implementa el criterio de saliencia §2 (un evento es saliente si cumple ≥2
señales). Automatiza las señales medibles desde el `EventCluster`; las que son
juicio humano (consecuencia de fondo) se aproximan con proxies léxicos, y la
multi-fuente queda inerte porque el corpus es mono-fuente (Andina). Esto es
selección automática del SISTEMA; el gold humano sigue siendo la referencia.

Mapa a §2:
  1. prominencia        — Humala en el título de ≥1 nota (pasaje).
  2. nota_dedicada      — proxy: ≥2 notas cubren el evento (cobertura dedicada).
  3. cobertura_sostenida— ≥2 fechas de publicación distintas.
  4. consecuencia       — proxy léxico: el título refiere un hecho con efecto
                          (condena, sentencia, prisión, orden judicial, …).
  5. multi_fuente [bonus]— ≥2 medios independientes. Inerte: mono-fuente.
"""

from __future__ import annotations

import re

from src.schemas import EventCluster

_SUJETO = re.compile(r"\b(humala|ollanta)\b", re.IGNORECASE)
_CONSECUENCIA = re.compile(
    r"conden|sentenc|prisi[oó]n|absuel|orden[oó]|dicta|enjuiciamiento|acusaci[oó]n|"
    r"reparaci[oó]n|inhabilit|detenci[oó]n|captura|impedimento|prisi[oó]n preventiva|"
    r"fallo|allanamiento|fianza|comparecencia",
    re.IGNORECASE,
)

UMBRAL_SENALES = 2   # §2: saliente si cumple ≥2


def senales(c: EventCluster) -> dict[str, bool]:
    """Evalúa las señales de saliencia §2 sobre un cluster."""
    pasajes = " || ".join(c.pasajes_evidencia)
    return {
        "prominencia": bool(_SUJETO.search(pasajes)),
        "nota_dedicada": len(c.fuentes) >= 2,
        "cobertura_sostenida": len(set(c.fechas_evidencia)) >= 2,
        "consecuencia": bool(_CONSECUENCIA.search(pasajes)),
        "multi_fuente": False,   # corpus mono-fuente; bonus inerte por ahora
    }


def es_saliente(c: EventCluster) -> bool:
    """True si el cluster cumple ≥2 señales (§2)."""
    return sum(senales(c).values()) >= UMBRAL_SENALES


def select_salient(clusters: list[EventCluster]) -> list[EventCluster]:
    """Selecciona los clusters de evento salientes (orden cronológico preservado)."""
    return [c for c in clusters if es_saliente(c)]
