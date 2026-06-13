"""Ingesta — colector Agencia Andina (andina.pe).

Busca notas de la agencia estatal peruana y las mapea a `Documento` (con cuerpo
real, a diferencia de GDELT). Verifica robots.txt ANTES de scrapear cada URL
( §9) y respeta la fecha de corte.

Nota: el HTML de andina.pe puede cambiar; los selectores son el punto frágil a
revisar al escalar.
"""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from src.ingest._util import (
    dentro_de_corte,
    get_with_backoff,
    http_session,
    puede_scrapear,
)
from src.schemas import Documento

BASE = "https://andina.pe"
BUSQUEDA = BASE + "/agencia/resultados.aspx?cat=&op={consulta}"


def _parse_fecha(texto: str) -> date | None:
    """Intenta varios formatos de fecha presentes en las notas."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def _urls_resultados(session, consulta: str, limite: int) -> list[str]:
    """Lista de URLs de notas desde la página de resultados de búsqueda."""
    url = BUSQUEDA.format(consulta=quote_plus(consulta))
    if not puede_scrapear(url):
        return []
    resp = get_with_backoff(session, url)
    sopa = BeautifulSoup(resp.text, "lxml")
    urls: list[str] = []
    for a in sopa.select("a[href*='/agencia/noticia-']"):
        href = a.get("href", "")
        if href.startswith("/"):
            href = BASE + href
        if href not in urls:
            urls.append(href)
        if len(urls) >= limite:
            break
    return urls


def _parse_nota(session, url: str) -> Documento | None:
    """Descarga y parsea una nota individual a `Documento`."""
    if not puede_scrapear(url):
        return None
    resp = get_with_backoff(session, url)
    sopa = BeautifulSoup(resp.text, "lxml")

    titulo_el = sopa.select_one("h1")
    cuerpo_els = sopa.select("article p") or sopa.select(".caja-nota p")
    fecha_el = sopa.select_one("time, .fecha")

    if not titulo_el or not cuerpo_els:
        return None
    titulo = titulo_el.get_text(strip=True)
    cuerpo = "\n".join(p.get_text(strip=True) for p in cuerpo_els)
    fecha_attr = (fecha_el.get("datetime") if fecha_el else None) or (
        fecha_el.get_text(strip=True) if fecha_el else ""
    )
    fecha_pub = _parse_fecha(fecha_attr or "")
    if fecha_pub is None:
        return None

    return Documento(
        doc_id=f"andina:{url.rsplit('/', 1)[-1]}",
        fuente="andina.pe",
        url=url,
        fecha_pub=fecha_pub,
        texto=f"{titulo}\n{cuerpo}".strip(),
    )


def collect(nombre: str, hasta: date, *, limite: int = 50) -> list[Documento]:
    """Recolecta documentos de Andina para `nombre` hasta la fecha de corte."""
    session = http_session()
    docs: list[Documento] = []
    for url in _urls_resultados(session, nombre, limite):
        doc = _parse_nota(session, url)
        if doc is None:
            continue
        if not dentro_de_corte(doc.fecha_pub, hasta):
            continue
        docs.append(doc)
        if len(docs) >= limite:
            break
    return docs
