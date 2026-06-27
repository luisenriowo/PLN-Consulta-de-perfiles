"""Crawler por ID de Andina — ingesta a ESCALA, multi-tema (crawl completo).

La búsqueda de andina.pe está capada a ~300 resultados/query y a ~2021, así que
NO sirve para un corpus completo. Pero las URLs de nota son
`andina.pe/agencia/noticia-<slug>-<id>.aspx` con ID numérico secuencial, y el
sitio acepta CUALQUIER slug: `noticia-x-<id>.aspx` redirige a la nota correcta.
Enumerando IDs se obtiene TODO lo alcanzable, incluido el histórico anterior a
2021 que la búsqueda no devuelve.

Resumable: checkpoint con el último ID procesado + JSONL incremental. Reanudar es
volver a correr el mismo comando. Respeta robots.txt (Allow: /) vía
`andina.parse_nota` y aplica cortesía (`--delay`) entre peticiones.

⚠ El espacio de IDs ronda el millón → un crawl completo es un job de DÍAS. Córrelo
acotado por rangos (`--desde-id`/`--hasta-id`) y/o en background, reanudable.

Uso:
  python scripts/crawl_andina.py --desde-id 900000 --hasta-id 1010000
  python scripts/crawl_andina.py --desde-id 900000 --hasta-id 1010000 --salida data/andina_crawl.jsonl --delay 0.5
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date
from pathlib import Path

from src.ingest import andina
from src.ingest._util import dentro_de_ventana, http_session

log = logging.getLogger(__name__)

URL = "https://andina.pe/agencia/noticia-x-{id}.aspx"


def crawl(
    desde_id: int, hasta_id: int, salida: Path, *, delay: float = 0.5,
    limite: int | None = None, ckpt_cada: int = 50,
    desde: date | None = None, hasta: date | None = None,
) -> dict:
    """Recorre [desde_id, hasta_id] descargando notas válidas a `salida` (JSONL).

    Si se dan `desde`/`hasta`, solo se ESCRIBEN las notas cuya fecha de
    publicación cae en la ventana (las fuera de ventana igual cuestan una
    petición: el ID no revela la fecha sin descargar). Reanuda desde el
    checkpoint. Devuelve estadísticas finales.
    """
    ckpt = salida.with_suffix(".ckpt.json")
    estado = (
        json.loads(ckpt.read_text(encoding="utf-8"))
        if ckpt.exists() else {"ultimo_id": desde_id - 1, "ok": 0, "vistos": 0}
    )
    inicio = max(desde_id, estado["ultimo_id"] + 1)
    ok, vistos = estado["ok"], estado["vistos"]
    if inicio > hasta_id:
        log.info("nada que hacer: checkpoint (%d) ya cubre el rango", estado["ultimo_id"])
        return estado

    salida.parent.mkdir(parents=True, exist_ok=True)
    session = http_session()
    log.info("crawl IDs [%d … %d] → %s (reanudando en %d)", desde_id, hasta_id, salida, inicio)

    t0 = time.time()
    i = inicio
    with salida.open("a", encoding="utf-8") as f:
        try:
            for i in range(inicio, hasta_id + 1):
                vistos += 1
                try:
                    doc = andina.parse_nota(session, URL.format(id=i))
                except Exception:
                    doc = None   # 404 / id inexistente / error de red puntual
                en_ventana = doc is not None and (
                    (desde is None and hasta is None)
                    or dentro_de_ventana(
                        doc.fecha_pub,
                        desde=desde or date.min, hasta=hasta or date.max,
                    )
                )
                if doc is not None and doc.texto.strip() and en_ventana:
                    f.write(json.dumps({
                        "doc_id": doc.doc_id, "fuente": doc.fuente, "url": doc.url,
                        "fecha_pub": doc.fecha_pub.isoformat(), "texto": doc.texto,
                    }, ensure_ascii=False) + "\n")
                    ok += 1
                if vistos % ckpt_cada == 0:
                    f.flush()
                    ckpt.write_text(json.dumps({"ultimo_id": i, "ok": ok, "vistos": vistos}),
                                    encoding="utf-8")
                    rate = vistos / max(time.time() - t0, 1e-9)
                    log.info("id=%d  válidas=%d/%d (%.0f%%)  %.1f ids/s",
                             i, ok, vistos, 100 * ok / vistos, rate)
                if limite and ok >= limite:
                    break
                time.sleep(delay)
        finally:
            ckpt.write_text(json.dumps({"ultimo_id": i, "ok": ok, "vistos": vistos}),
                            encoding="utf-8")

    dur = time.time() - t0
    log.info("== FIN == válidas=%d de %d vistos en %.0fs (%.1f ids/s)",
             ok, vistos, dur, vistos / max(dur, 1e-9))
    return {"ultimo_id": i, "ok": ok, "vistos": vistos, "segundos": round(dur, 1)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="Crawler por ID de Andina")
    p.add_argument("--desde-id", type=int, required=True)
    p.add_argument("--hasta-id", type=int, required=True)
    p.add_argument("--salida", type=Path, default=Path("data/andina_crawl.jsonl"))
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--limite", type=int, default=None, help="parar tras N notas válidas")
    p.add_argument("--desde", type=date.fromisoformat, default=None, help="fecha mínima ISO")
    p.add_argument("--hasta", type=date.fromisoformat, default=None, help="fecha máxima ISO")
    args = p.parse_args()
    crawl(args.desde_id, args.hasta_id, args.salida, delay=args.delay,
          limite=args.limite, desde=args.desde, hasta=args.hasta)
