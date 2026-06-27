"""Backbone — Selección de saliencia (FIJO, compartido por las 4 condiciones).

Selecciona los `EventCluster` salientes que entran a la línea de tiempo. Es la
última etapa antes del punto de swap: su salida es idéntica para las 4
condiciones, así que NO debe sesgar la comparación.

Implementa el criterio de saliencia §2 (un evento es saliente si cumple ≥2
señales). Automatiza las señales medibles desde el `EventCluster`; las que son
juicio humano (consecuencia de fondo) se aproximan con proxies léxicos, y la
multi-fuente queda inerte porque el corpus es mono-fuente (Andina). Esto es
selección automática del SISTEMA; el gold humano sigue siendo la referencia.

El módulo es AGNÓSTICO al sujeto: la señal de prominencia se evalúa contra un
`sujeto_patron` que pasa el llamador (construido con `patron_sujeto`). En modo
figura el script pasa las formas superficiales del sujeto; en modo tema-céntrico
no hay sujeto único, así que `sujeto_patron=None` deja la prominencia inerte y
la saliencia se apoya en las otras señales.

Mapa a §2:
  1. prominencia        — el sujeto aparece en el título de ≥1 nota (pasaje).
  2. nota_dedicada      — proxy: ≥2 notas cubren el evento (cobertura dedicada).
  3. cobertura_sostenida— ≥2 fechas de publicación distintas.
  4. consecuencia       — proxy léxico: el título refiere un hecho con efecto
                          (condena, sentencia, prisión, orden judicial, …).
  5. multi_fuente [bonus]— el evento está corroborado por ≥2 FAMILIAS de fuente
                          (p. ej. andina + gdelt), derivadas del prefijo del
                          `doc_id` namespaced. En corpus mono-fuente queda en
                          False (compatibilidad hacia atrás).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.pipeline._utils import _norm
from src.schemas import EventCluster

_CONSECUENCIA = re.compile(
    r"conden|sentenc|prisi[oó]n|absuel|orden[oó]|dicta|enjuiciamiento|acusaci[oó]n|"
    r"reparaci[oó]n|inhabilit|detenci[oó]n|captura|impedimento|prisi[oó]n preventiva|"
    r"fallo|allanamiento|fianza|comparecencia",
    re.IGNORECASE,
)

UMBRAL_SENALES = 2   # §2: saliente si cumple ≥2


def _familia_fuente(doc_id: str) -> str:
    """Familia de fuente desde el doc_id namespaced: 'andina:123' -> 'andina',
    'gdelt:http://…' -> 'gdelt'. Sin prefijo, devuelve el id completo."""
    return doc_id.split(":", 1)[0] if ":" in doc_id else doc_id


def patron_sujeto(formas: Iterable[str]) -> re.Pattern | None:
    """Compila un patrón ``\\b(forma1|forma2|…)\\b`` de formas superficiales.

    Las formas se normalizan (minúsculas, sin acentos) para casar contra texto
    también normalizado vía `_norm`. Devuelve None si no quedan formas válidas:
    en ese caso la señal de prominencia queda inerte (modo tema-céntrico).
    """
    formas_norm = sorted(
        {_norm(f) for f in formas if f and f.strip()}, key=len, reverse=True
    )
    if not formas_norm:
        return None
    alternativas = "|".join(re.escape(f) for f in formas_norm)
    return re.compile(rf"\b({alternativas})\b")


def senales(
    c: EventCluster, *, sujeto_patron: re.Pattern | None = None
) -> dict[str, bool]:
    """Evalúa las señales de saliencia §2 sobre un cluster.

    `sujeto_patron` controla la señal de prominencia; si es None la señal queda
    en False (no hay sujeto único contra el cual medir prominencia).
    """
    pasajes = " || ".join(c.pasajes_evidencia)
    prominencia = (
        bool(sujeto_patron.search(_norm(pasajes))) if sujeto_patron is not None else False
    )
    medios = {_familia_fuente(f) for f in c.fuentes}
    return {
        "prominencia": prominencia,
        "nota_dedicada": len(c.fuentes) >= 2,
        "cobertura_sostenida": len(set(c.fechas_evidencia)) >= 2,
        "consecuencia": bool(_CONSECUENCIA.search(pasajes)),
        "multi_fuente": len(medios) >= 2,
    }


def es_saliente(c: EventCluster, *, sujeto_patron: re.Pattern | None = None) -> bool:
    """True si el cluster cumple ≥2 señales (§2)."""
    return sum(senales(c, sujeto_patron=sujeto_patron).values()) >= UMBRAL_SENALES


def select_salient(
    clusters: list[EventCluster], *, sujeto_patron: re.Pattern | None = None
) -> list[EventCluster]:
    """Selecciona los clusters de evento salientes (orden cronológico preservado)."""
    return [c for c in clusters if es_saliente(c, sujeto_patron=sujeto_patron)]
