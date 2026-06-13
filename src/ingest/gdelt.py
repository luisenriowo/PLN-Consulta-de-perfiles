"""Ingesta — colector GDELT (DOC 2.0 API).

Recupera cobertura de noticias en español y la mapea a `Documento`. GDELT da
metadatos reales (title, url, dominio, fecha vista) → buen ajuste con `fecha_pub`,
pero NO entrega el cuerpo del artículo: `texto` queda con el titular. Para
profundidad histórica (Humala abarca ~4 décadas) hay que ir a GDELT en BigQuery;
la DOC API solo cubre de forma fiable los últimos ~meses (eso es 'escalar').

Respeta robots.txt vía la API oficial y la fecha de corte ( §1, §9).
"""

from __future__ import annotations

from datetime import date, datetime

from src.ingest._util import dentro_de_corte, get_with_backoff, http_session
from src.schemas import Documento

API = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_seendate(s: str) -> date:
    """'20251231T120000Z' → date."""
    return datetime.strptime(s, "%Y%m%dT%H%M%SZ").date()


def collect(nombre: str, hasta: date, *, maxrecords: int = 75) -> list[Documento]:
    """Recolecta documentos de GDELT para `nombre` hasta la fecha de corte."""
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
            "enddatetime": hasta.strftime("%Y%m%d") + "235959",
        },
    )
    articulos = resp.json().get("articles", [])
    docs: list[Documento] = []
    for art in articulos:
        try:
            fecha_pub = _parse_seendate(art["seendate"])
        except (KeyError, ValueError):
            continue
        if not dentro_de_corte(fecha_pub, hasta):
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
