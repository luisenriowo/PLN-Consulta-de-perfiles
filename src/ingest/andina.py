"""Ingesta — colector Agencia Andina (andina.pe).

Selectores verificados sobre el sitio real (2026-06):
  - Búsqueda: GET `https://andina.pe/agencia/busqueda.aspx?search=<consulta>`
    (el formulario de cabecera hace postback y redirige a esta URL GET).
  - URL de nota: `.../noticia-<slug>-<id>.aspx`.
  - Título:  `h1`.
  - Fecha:   `meta[property="article:published_time"]` (ISO 8601).
  - Lead:    `meta[property="og:description"]`.
  - Cuerpo:  `div.linknotas` (texto suelto, no en <p>).

⚠ LIMITACIÓN CONOCIDA (medida): la búsqueda ordena por RELEVANCIA, sin filtro de
fecha, y la paginación es solo por postback ASP.NET con tope de 15 páginas (~300
resultados). `buscar` conduce ese postback y recolecta el set completo. Para el
sujeto "Ollanta Humala" eso cubre 2021-06 … 2026-05 (toda la era judicial
Odebrecht), pero NO llega a 2006/2011. La profundidad mayor exige otra vía
(GDELT/BigQuery), fuera de alcance por decisión del proyecto.

robots.txt de andina.pe = `Allow: /`; aun así verificamos antes de cada fetch
(CLAUDE.md §9) y respetamos la ventana temporal.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from src.ingest._util import (
    dentro_de_ventana,
    get_with_backoff,
    http_session,
    puede_scrapear,
)
from src.schemas import Documento

BASE = "https://andina.pe/agencia/"
BUSQUEDA = BASE + "busqueda.aspx"
_RE_NOTA = re.compile(r"noticia-.*-\d+\.aspx$")
_RE_ID = re.compile(r"-(\d+)\.aspx$")
# Ruido a podar del cuerpo (widgets incrustados y arte ASCII de comentarios).
_RUIDO = re.compile(r"/{3,}|LAS M[ÁA]S LE[ÍI]DAS|M[áa]s en Andina", re.IGNORECASE)


_RE_TARGET = re.compile(r"__doPostBack\('([^']+)'")


def _absolutizar(href: str) -> str:
    href = href.split("?", 1)[0]
    if href.startswith("http"):
        return href
    return BASE + re.sub(r"^/?(agencia/)?", "", href)


def _campos_ocultos(sopa: BeautifulSoup) -> dict[str, str]:
    """Todos los inputs (incluye __VIEWSTATE) para reenviar en el postback."""
    return {i["name"]: i.get("value", "") for i in sopa.find_all("input") if i.get("name")}


def _targets_pager(sopa: BeautifulSoup) -> dict[str, str]:
    """Mapa etiqueta_de_página -> __EVENTTARGET del paginador ASP.NET."""
    out: dict[str, str] = {}
    for a in sopa.select("a[href*=dlPaging]"):
        m = _RE_TARGET.search(a.get("href", ""))
        if m:
            out[a.get_text(strip=True)] = m.group(1)
    return out


def buscar(session, consulta: str, *, max_paginas: int = 15) -> list[str]:
    """URLs de notas para `consulta`, conduciendo la paginación postback.

    Recorre hasta `max_paginas` páginas de resultados (tope real del sitio ≈ 15).
    """
    if not puede_scrapear(BUSQUEDA):
        return []
    resp = get_with_backoff(session, BUSQUEDA, params={"search": consulta})
    sopa = BeautifulSoup(resp.text, "lxml")
    urls: list[str] = []
    for pagina in range(1, max_paginas + 1):
        for a in sopa.find_all("a", href=True):
            if _RE_NOTA.search(a["href"]):
                u = _absolutizar(a["href"])
                if u not in urls:
                    urls.append(u)
        targets = _targets_pager(sopa)
        siguiente = str(pagina + 1)
        if siguiente not in targets:
            break
        datos = _campos_ocultos(sopa)
        datos["__EVENTTARGET"] = targets[siguiente]
        datos["__EVENTARGUMENT"] = ""
        resp = session.post(BUSQUEDA, params={"search": consulta}, data=datos, timeout=30)
        sopa = BeautifulSoup(resp.text, "lxml")
    return urls


def _parse_fecha(meta_iso: str) -> date | None:
    try:
        return datetime.fromisoformat(meta_iso.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _limpiar_cuerpo(texto: str) -> str:
    lineas = [ln.strip() for ln in texto.splitlines()]
    return " ".join(ln for ln in lineas if ln and not _RUIDO.search(ln))


def parse_nota(session, url: str) -> Documento | None:
    """Descarga y parsea una nota individual a `Documento` (None si falla)."""
    if not puede_scrapear(url):
        return None
    resp = get_with_backoff(session, url)
    sopa = BeautifulSoup(resp.text, "lxml")

    h1 = sopa.find("h1")
    meta_fecha = sopa.select_one('meta[property="article:published_time"]')
    meta_lead = sopa.select_one('meta[property="og:description"]')
    cuerpo_el = sopa.select_one("div.linknotas")
    if h1 is None or meta_fecha is None:
        return None
    fecha_pub = _parse_fecha(meta_fecha.get("content", ""))
    if fecha_pub is None:
        return None

    titulo = h1.get_text(strip=True)
    lead = meta_lead.get("content", "").strip() if meta_lead else ""
    cuerpo = ""
    if cuerpo_el:
        for w in cuerpo_el.select("script, style, blockquote, iframe, ins, .twitter-tweet"):
            w.decompose()
        cuerpo = _limpiar_cuerpo(cuerpo_el.get_text("\n", strip=True))

    partes = [p for p in (titulo, lead, cuerpo) if p]
    id_nota = (_RE_ID.search(url) or [None, url])[1]
    return Documento(
        doc_id=f"andina:{id_nota}",
        fuente="andina.pe",
        url=url,
        fecha_pub=fecha_pub,
        texto="\n".join(partes).strip(),
    )


def collect(
    nombre: str, hasta: date, *, max_paginas: int = 15, limite: int | None = None
) -> list[Documento]:
    """Recolecta documentos de Andina para `nombre` dentro de la ventana.

    Conduce la paginación de la búsqueda (hasta `max_paginas`) y descarga el
    cuerpo de cada nota. `limite` recorta el total de documentos resultantes.
    Nota: alcance temporal limitado por la búsqueda del sitio (ver docstring).
    """
    session = http_session()
    docs: list[Documento] = []
    for url in buscar(session, nombre, max_paginas=max_paginas):
        doc = parse_nota(session, url)
        if doc is None or not dentro_de_ventana(doc.fecha_pub, hasta=hasta):
            continue
        docs.append(doc)
        if limite is not None and len(docs) >= limite:
            break
    return docs
