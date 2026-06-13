"""Utilidades compartidas por los colectores de ingesta.

No es un colector: solo helpers (User-Agent, sesión HTTP con reintentos,
robots.txt y aplicación de la fecha de corte). Mantener fino.
"""

from __future__ import annotations

import time
import urllib.robotparser
from datetime import date
from urllib.parse import urlparse

import requests

# Fecha de corte FIJA de la evaluación sobre Ollanta Humala ( §1).
# Congelada para reproducibilidad: el corpus no incluye nada posterior.
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


def puede_scrapear(url: str, *, user_agent: str = USER_AGENT) -> bool:
    """Consulta robots.txt del dominio antes de scrapear ( §9)."""
    partes = urlparse(url)
    robots_url = f"{partes.scheme}://{partes.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # Si robots.txt no se puede leer, somos conservadores: no scrapear.
        return False
    return rp.can_fetch(user_agent, url)


def dentro_de_corte(fecha_pub: date, hasta: date) -> bool:
    """True si el documento es publicado en o antes de la fecha de corte."""
    return fecha_pub <= hasta
