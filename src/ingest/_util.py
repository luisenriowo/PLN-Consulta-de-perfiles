"""Utilidades compartidas por los colectores de ingesta.

No es un colector: solo helpers (User-Agent, sesión HTTP con reintentos,
robots.txt y aplicación de la fecha de corte). Mantener fino.
"""

from __future__ import annotations

import functools
import time
import urllib.robotparser
from datetime import date
from urllib.parse import urlparse

import requests

# Ventana FIJA de la evaluación sobre Ollanta Humala ( §1).
# Congelada para reproducibilidad: el corpus no incluye nada fuera de ella.
# Inicio en 2021: es el piso REAL alcanzable por la búsqueda de Andina para el
# sujeto (medido: 2021-06 … 2026-05, ver memoria andina-search-feasibility).
# Cubre toda la era judicial Odebrecht (juicio 2022→, condena 2025), que es el
# núcleo del caso disputado. 2006/2011 no son alcanzables sin BigQuery.
FECHA_INICIO_HUMALA: date = date(2021, 1, 1)
FECHA_CORTE_HUMALA: date = date(2025, 12, 31)

# Identificación honesta del bot (uso académico). Permite que los sitios nos
# distingan y que respetemos su política.
USER_AGENT = "timeline-gen/0.1 (proyecto académico PUCP; PLN T02)"


def http_session() -> requests.Session:
    """Sesión `requests` con User-Agent fijo."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def get_with_backoff(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    max_tries: int = 4,
    base_delay: float = 2.0,
    timeout: int = 30,
) -> requests.Response:
    """GET con reintentos y backoff exponencial ante 429/5xx."""
    last_exc: Exception | None = None
    for intento in range(max_tries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(
                    f"{resp.status_code} reintentable", response=resp
                )
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # noqa: PERF203
            last_exc = exc
            if intento < max_tries - 1:
                time.sleep(base_delay * (2**intento))
    assert last_exc is not None
    raise last_exc


@functools.lru_cache(maxsize=32)
def _robots(scheme: str, netloc: str) -> urllib.robotparser.RobotFileParser | None:
    """Parser de robots.txt cacheado por dominio (un solo fetch por host)."""
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{scheme}://{netloc}/robots.txt")
    try:
        rp.read()
    except Exception:
        return None
    return rp


def puede_scrapear(url: str, *, user_agent: str = USER_AGENT) -> bool:
    """Consulta robots.txt del dominio antes de scrapear ( §9)."""
    partes = urlparse(url)
    rp = _robots(partes.scheme, partes.netloc)
    if rp is None:
        # Si robots.txt no se puede leer, somos conservadores: no scrapear.
        return False
    return rp.can_fetch(user_agent, url)


def dentro_de_corte(fecha_pub: date, hasta: date) -> bool:
    """True si el documento es publicado en o antes de la fecha de corte."""
    return fecha_pub <= hasta


def dentro_de_ventana(
    fecha_pub: date,
    *,
    desde: date = FECHA_INICIO_HUMALA,
    hasta: date = FECHA_CORTE_HUMALA,
) -> bool:
    """True si el documento cae dentro de la ventana cerrada [desde, hasta]."""
    return desde <= fecha_pub <= hasta
