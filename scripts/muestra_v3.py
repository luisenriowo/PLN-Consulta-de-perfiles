"""Crea una MUESTRA estratificada por año del corpus v3 (todos los años) y filtra
sus menciones NER persistidas, para construir un grafo multi-anual GARANTIZADO en
tiempo acotado (sin esperar al build completo).

Uso:   python scripts/muestra_v3.py [docs_por_anio=8000]
Salida: data/corpus_andina_v3s.parquet  +  data/menciones_corpus_andina_v3s/
Luego:  python scripts/build_open_graph.py andina-v3s --corpus-slug andina_v3s --menciones --top-n 150
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src import manifiesto

PER_YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
SRC, DST = "andina_v3", "andina_v3s"

df = pd.read_parquet(manifiesto.corpus_path(SRC))
df["_y"] = pd.to_datetime(df["fecha_pub"]).dt.year
sample = (
    pd.concat([g.sample(min(PER_YEAR, len(g)), random_state=42) for _, g in df.groupby("_y")])
    .drop(columns=["_y"])
    .reset_index(drop=True)
)
sample.to_parquet(manifiesto.corpus_path(DST), index=False)
keep = set(sample["doc_id"])
por_anio = (
    sample.assign(y=pd.to_datetime(sample["fecha_pub"]).dt.year)["y"]
    .value_counts()
    .sort_index()
    .to_dict()
)
print(f"corpus muestra: {len(sample)} docs  por_anio={por_anio}", flush=True)

# --- filtrar menciones a los doc_ids de la muestra (parte por parte, memoria segura) ---
src_mdir = Path("data") / "menciones_corpus_andina_v3"
dst_mdir = Path("data") / "menciones_corpus_andina_v3s"
dst_mdir.mkdir(parents=True, exist_ok=True)
for p in dst_mdir.glob("part-*.parquet"):
    p.unlink()

buf: list[pd.DataFrame] = []
out_i = total = 0


def flush():
    global buf, out_i, total
    if not buf:
        return
    out = pd.concat(buf, ignore_index=True)
    out.to_parquet(dst_mdir / f"part-{out_i:05d}.parquet", index=False)
    out_i += 1
    total += len(out)
    buf = []


for p in sorted(src_mdir.glob("part-*.parquet")):
    m = pd.read_parquet(p)
    m = m[m["doc_id"].isin(keep)]
    if len(m):
        buf.append(m)
    if sum(len(b) for b in buf) >= 500_000:
        flush()
flush()
print(f"menciones muestra: {total} -> {dst_mdir}", flush=True)
