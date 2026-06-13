"""Ingesta — colector Wikipedia (es) vía MediaWiki API.

Recupera el artículo de la figura (y relacionados) TAL COMO EXISTÍA en la fecha
de corte —no la versión actual— y lo parte en párrafos -> `Documento`. Tomar la
revisión `as-of` cumple dos cosas: respeta la fecha de corte ( §1) y
evita que ediciones posteriores al corte filtren conocimiento futuro al corpus,
lo que contaminaría la evaluación de fidelidad.

Wikipedia es material de REFERENCIA: `fecha_pub` = fecha de esa revisión (DCT
proxy). Las fechas reales de los eventos viven en la prosa y las resolverá
`pipeline/temporal.py`.
"""

from __future__ import annotations

from datetime import date, datetime

from bs4 import BeautifulSoup

from src.ingest._util import get_with_backoff, http_session
from src.schemas import Documento

API = "https://es.wikipedia.org/w/api.php"

# Relacionados que aseguran diversidad de entidades de la familia (clave para
# probar el entity linking). Solo se usan cuando el sujeto es Ollanta Humala.
_RELACIONADOS_HUMALA = ["Nadine Heredia", "Antauro Humala"]

_MIN_PARRAFO = 120  # caracteres; descarta líneas sueltas / encabezados


def _revision_en_corte(
    session, titulo: str, hasta: date
) -> tuple[int, int, date] | None:
    """(pageid, oldid, fecha) de la última revisión <= corte; None si no hay."""
    resp = get_with_backoff(
        session,
        API,
        params={
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "prop": "revisions",
            "titles": titulo,
            "redirects": 1,
            "rvprop": "ids|timestamp",
            "rvlimit": 1,
            "rvdir": "older",
            "rvstart": hasta.strftime("%Y-%m-%d") + "T23:59:59Z",
        },
    )
    paginas = resp.json().get("query", {}).get("pages", [])
    for pag in paginas:
        revs = pag.get("revisions")
        if pag.get("missing") or not revs:
            continue
        ts = revs[0]["timestamp"]
        fecha = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
        return pag["pageid"], revs[0]["revid"], fecha
    return None


def _parrafos_de_oldid(session, oldid: int) -> list[str]:
    """HTML renderizado de una revisión concreta -> párrafos de texto plano."""
    resp = get_with_backoff(
        session,
        API,
        params={
            "action": "parse",
            "format": "json",
            "formatversion": 2,
            "oldid": oldid,
            "prop": "text",
            "disabletoc": 1,
        },
    )
    html = resp.json().get("parse", {}).get("text", "")
    sopa = BeautifulSoup(html, "lxml")
    parrafos: list[str] = []
    for p in sopa.select("p"):
        texto = p.get_text(" ", strip=True)
        if len(texto) >= _MIN_PARRAFO:
            parrafos.append(texto)
    return parrafos


def collect(nombre: str, hasta: date, *, limite: int | None = None) -> list[Documento]:
    """Recolecta documentos de Wikipedia (snapshot a `hasta`) para `nombre`.

    Cada párrafo del artículo (y de los relacionados, para Humala) es un
    `Documento`. `limite` recorta el total (útil para smoke).
    """
    session = http_session()
    titulos = [nombre]
    if "humala" in nombre.lower():
        titulos += _RELACIONADOS_HUMALA

    docs: list[Documento] = []
    for titulo in titulos:
        rev = _revision_en_corte(session, titulo, hasta)
        if rev is None:
            continue
        pageid, oldid, fecha_pub = rev
        url = f"https://es.wikipedia.org/?curid={pageid}&oldid={oldid}"
        for i, parrafo in enumerate(_parrafos_de_oldid(session, oldid)):
            docs.append(
                Documento(
                    doc_id=f"wiki:{pageid}:{oldid}:{i}",
                    fuente="es.wikipedia.org",
                    url=url,
                    fecha_pub=fecha_pub,
                    texto=parrafo,
                )
            )
            if limite is not None and len(docs) >= limite:
                return docs
    return docs
