"""NER en batch sobre el corpus congelado, con PERSISTENCIA de menciones (F2).

El NER es el cuello de cómputo del pipeline; persistir las menciones evita
re-correrlo en cada iteración (entidades, co-ocurrencias, etc.). Usa el modelo
NER configurado por entorno (`NER_MODEL=spacy|transformer`); con GPU + torch CUDA,
`NER_MODEL=transformer` corre en GPU automáticamente (ver `ner._ner_device`).

Salida: un directorio de parquets por chunk (resumable: salta los ya hechos):
  data/menciones_<stem>/part-00000.parquet …   columnas: doc_id, inicio, fin, texto, tipo

Uso:
  NER_MODEL=transformer python scripts/ner_corpus.py --corpus data/corpus_andina_v1.parquet
  python scripts/ner_corpus.py --corpus data/corpus_andina_v1.parquet --chunk 500 --limite 200
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import pandas as pd

from src.pipeline.ner import get_ner_model

log = logging.getLogger(__name__)


def _dir_salida(corpus: Path) -> Path:
    # corpus_andina_v1.parquet -> data/menciones_corpus_andina_v1/
    return corpus.parent / f"menciones_{corpus.stem}"


def correr(corpus: Path, *, chunk: int = 500, limite: int | None = None) -> Path:
    df = pd.read_parquet(corpus, columns=["doc_id", "texto"])
    if limite:
        df = df.head(limite)
    out = _dir_salida(corpus)
    out.mkdir(parents=True, exist_ok=True)
    hechos = {
        int(p.stem.split("-")[1]) for p in out.glob("part-*.parquet")
    }
    ner = get_ner_model()
    n_chunks = (len(df) + chunk - 1) // chunk
    log.info("corpus=%d docs  chunks=%d (size %d)  ya hechos=%d  salida=%s",
             len(df), n_chunks, chunk, len(hechos), out)

    t0 = time.time()
    total_menc = 0
    for ci in range(n_chunks):
        if ci in hechos:
            continue
        sub = df.iloc[ci * chunk:(ci + 1) * chunk]
        textos = sub["texto"].tolist()
        doc_ids = sub["doc_id"].tolist()
        filas = []
        for doc_id, menciones in zip(doc_ids, ner(textos)):
            for m in menciones:
                filas.append((doc_id, m.inicio, m.fin, m.texto, m.tipo))
        pd.DataFrame(filas, columns=["doc_id", "inicio", "fin", "texto", "tipo"]) \
          .to_parquet(out / f"part-{ci:05d}.parquet", index=False)
        total_menc += len(filas)
        if ci % 10 == 0 or ci == n_chunks - 1:
            rate = (ci + 1) * chunk / max(time.time() - t0, 1e-9)
            log.info("  chunk %d/%d  menciones=%d  ~%.0f docs/s", ci + 1, n_chunks, total_menc, rate)
    log.info("== LISTO == menciones nuevas=%d en %.0fs", total_menc, time.time() - t0)
    return out


def cargar_menciones(dir_o_corpus: Path) -> list[tuple[str, str, str]]:
    """Carga las menciones persistidas como (texto, tipo, doc_id) para
    `descubrir_entidades(..., menciones=...)`. Acepta el dir de menciones o el
    parquet del corpus (deriva el dir)."""
    d = dir_o_corpus if dir_o_corpus.is_dir() else _dir_salida(dir_o_corpus)
    partes = sorted(d.glob("part-*.parquet"))
    if not partes:
        raise FileNotFoundError(f"No hay menciones en {d}; corre ner_corpus.py primero.")
    df = pd.concat((pd.read_parquet(p) for p in partes), ignore_index=True)
    return list(zip(df["texto"], df["tipo"], df["doc_id"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(description="NER en batch con persistencia de menciones")
    p.add_argument("--corpus", type=Path, default=Path("data/corpus_andina_v1.parquet"))
    p.add_argument("--chunk", type=int, default=500)
    p.add_argument("--limite", type=int, default=None, help="solo las primeras N notas (test)")
    args = p.parse_args()
    correr(args.corpus, chunk=args.chunk, limite=args.limite)
