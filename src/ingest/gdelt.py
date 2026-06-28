"""Ingesta — colector GDELT (DOC 2.0 API).

Fuente SECUNDARIA: aporta medios INDEPENDIENTES (no andina.pe) para corroborar
eventos → habilita la señal de saliencia multi-fuente (bonus). GDELT da
metadatos reales (title, url, dominio, fecha) pero NO el cuerpo: `texto` = titular.

⚠ Rate limit medido: la DOC API exige **1 request cada ≥5 s** (si no, 429
"Please limit requests to one every 5 seconds"). Por eso usamos backoff base 6 s.
La DOC API admite rango con start/enddatetime (≈2017→), suficiente para la
ventana 2021–2025; la profundidad mayor exigiría BigQuery (fuera de alcance).
"""

from __future__ import annotations

from datetime import date, datetime

from src.ingest._util import (
    FECHA_CORTE_HUMALA,
    FECHA_INICIO_HUMALA,
    dentro_de_ventana,
    get_with_backoff,
    http_session,
)
from src.schemas import Documento

API = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_seendate(s: str) -> date:
    """'20251231T120000Z' → date."""
    return datetime.strptime(s, "%Y%m%dT%H%M%SZ").date()


def collect(
    nombre: str,
    hasta: date = FECHA_CORTE_HUMALA,
    *,
    desde: date = FECHA_INICIO_HUMALA,
    maxrecords: int = 250,
) -> list[Documento]:
    """Recolecta documentos de GDELT para `nombre` en la ventana [desde, hasta].

    Una sola request (con backoff ≥6 s por el rate limit). `maxrecords` ≤ 250.
    """
    session = http_session()
    resp = get_with_backoff(
        session,
        API,
        params={
            "query": f'"{nombre}" sourcelang:spanish',
            "mode": "ArtList",
            "format": "json",
            "maxrecords": maxrecords,
            "sort": "DateDesc",
            "startdatetime": desde.strftime("%Y%m%d") + "000000",
            "enddatetime": hasta.strftime("%Y%m%d") + "235959",
        },
        base_delay=6.0,
        max_tries=5,
    )
    articulos = resp.json().get("articles", [])
    docs: list[Documento] = []
    for art in articulos:
        try:
            fecha_pub = _parse_seendate(art["seendate"])
        except (KeyError, ValueError):
            continue
        if not dentro_de_ventana(fecha_pub, desde=desde, hasta=hasta):
            continue
        docs.append(
            Documento(
                doc_id=f"gdelt:{art.get('url', '')}",
                fuente=art.get("domain", "gdelt"),
                url=art.get("url", ""),
                fecha_pub=fecha_pub,
                texto=art.get("title", "").strip(),  # sin cuerpo: solo titular
            )
        )
    return docs
