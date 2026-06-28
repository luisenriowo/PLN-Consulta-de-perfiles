"""Consolida el crawl crudo (JSONL) en un CORPUS CONGELADO + manifiesto + stats.

F1 del roadmap (§Datos). Pipeline:
  andina_crawl.jsonl
    → preprocess.preprocess (dedup por firma de texto + quita bylines + min_chars)
      → filtro de idioma (es_espanol: descarta inglés)
        → parquet versionado + manifiesto (versión, hash, conteos, rango) + stats

El parquet + su hash es lo que cita el paper (reproducibilidad): todos los demás
componentes (NER, entidades, grafo) parten de ESTE artefacto congelado. Re-ejecutable
a medida que el crawl crece (sube la versión).

Uso:
  python scripts/consolidar_corpus.py --jsonl data/andina_crawl.jsonl --version v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.pipeline import preprocess
from src.pipeline.preprocess import es_espanol
from src.schemas import Documento

log = logging.getLogger(__name__)


def _cargar_jsonl(path: Path) -> list[Documento]:
    docs: list[Documento] = []
    with path.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            try:                       # el jsonl puede estar escribiéndose en vivo
                r = json.loads(linea)
            except json.JSONDecodeError:
                continue               # línea final incompleta → se omite
            docs.append(Documento(
                doc_id=r["doc_id"], fuente=r["fuente"], url=r["url"],
                fecha_pub=pd.Timestamp(r["fecha_pub"]).date(), texto=r["texto"],
            ))
    return docs


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stats(docs: list[Documento]) -> dict:
    fechas = sorted(d.fecha_pub for d in docs)
    por_mes = Counter(f.strftime("%Y-%m") for f in fechas)
    por_anio = Counter(f.year for f in fechas)
    largos = [len(d.texto) for d in docs]
    return {
        "rango_fechas": [fechas[0].isoformat(), fechas[-1].isoformat()] if fechas else None,
        "por_anio": dict(sorted(por_anio.items())),
        "notas_por_mes": dict(sorted(por_mes.items())),
        "long_media_chars": round(sum(largos) / len(largos)) if largos else 0,
        "long_mediana_chars": sorted(largos)[len(largos) // 2] if largos else 0,
    }


def consolidar(jsonl: Path, version: str, data_dir: Path) -> dict:
    log.info("cargando %s …", jsonl)
    raw = _cargar_jsonl(jsonl)
    n_raw = len(raw)
    log.info("crudas: %d", n_raw)

    limpios = preprocess.preprocess(raw)        # dedup firma + bylines + min_chars
    n_dedup = len(limpios)
    log.info("tras preprocess (dedup+bylines+min_chars): %d  (descartadas %d)",
             n_dedup, n_raw - n_dedup)

    es = [d for d in limpios if es_espanol(d.texto)]
    n_es = len(es)
    log.info("tras filtro de idioma (ES): %d  (descartadas EN/otro %d)", n_es, n_dedup - n_es)

    salida = data_dir / f"corpus_andina_{version}.parquet"
    pd.DataFrame([
        {"doc_id": d.doc_id, "fuente": d.fuente, "url": d.url,
         "fecha_pub": d.fecha_pub.isoformat(), "texto": d.texto}
        for d in es
    ]).to_parquet(salida, index=False)

    stats = _stats(es)
    manifest = {
        "version": version,
        "fecha_consolidacion": datetime.now().date().isoformat(),
        "fuente_jsonl": str(jsonl),
        "n_crudas": n_raw,
        "n_tras_dedup": n_dedup,
        "n_final_es": n_es,
        "tasa_dedup": round(1 - n_dedup / n_raw, 4) if n_raw else 0,
        "tasa_descarte_idioma": round((n_dedup - n_es) / n_dedup, 4) if n_dedup else 0,
        "sha256": _sha256(salida),
        "parquet": str(salida),
        "stats": stats,
    }
    man_path = data_dir / f"corpus_andina_{version}.manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("== CONGELADO == %s (%d notas)  sha256=%s…", salida, n_es, manifest["sha256"][:12])
    log.info("   rango: %s  | por año: %s", stats["rango_fechas"], stats["por_anio"])
    log.info("   manifiesto: %s", man_path)
    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="Consolida el crawl en un corpus congelado")
    p.add_argument("--jsonl", type=Path, default=Path("data/andina_crawl.jsonl"))
    p.add_argument("--version", default="v1")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    args = p.parse_args()
    consolidar(args.jsonl, args.version, args.data_dir)
