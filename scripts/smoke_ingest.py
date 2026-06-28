"""Smoke test: ingest (Wikipedia) -> preprocess -> entities, sobre N documentos.

No es parte del experimento ni del producto: solo verifica que el tramo inicial
del backbone corre de punta a punta y muestra una muestra del output. Para
escalar, cambiar la fuente a GDELT/Andina y el modelo a es_core_news_lg.

Uso:
    python scripts/smoke_ingest.py [N]
"""

from __future__ import annotations

import sys
from collections import Counter

from src.ingest import wikipedia
from src.ingest._util import FECHA_CORTE_HUMALA
from src.pipeline import entities, preprocess
from src.pipeline.preprocess import segmentar_oraciones

SUJETO = "Ollanta Humala"
MODELO_SMOKE = "es_core_news_md"  # rápido; producción usa es_core_news_lg


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    print(f"== INGEST · Wikipedia · '{SUJETO}' · corte {FECHA_CORTE_HUMALA} ==")
    crudos = wikipedia.collect(SUJETO, FECHA_CORTE_HUMALA, limite=n)
    print(f"  documentos crudos: {len(crudos)}")

    limpios = preprocess.preprocess(crudos)
    n_oraciones = sum(len(segmentar_oraciones(d.texto)) for d in limpios)
    print("== PREPROCESS ==")
    print(
        f"  tras limpieza/dedup: {len(limpios)}  ({len(crudos) - len(limpios)} descartados)"
    )
    print(f"  oraciones segmentadas: {n_oraciones}")

    anotados = entities.link_entities(limpios, modelo=MODELO_SMOKE)

    # --- estadísticas de entidades ---
    por_tipo: Counter[str] = Counter()
    canon: Counter[str] = Counter()
    sin_enlazar_per = 0
    for d in anotados:
        for e in d.entidades:
            por_tipo[e.tipo] += 1
            if e.entidad_nombre:
                canon[e.entidad_nombre] += 1
            elif e.tipo == "PER":
                sin_enlazar_per += 1
    print(f"== ENTITIES · NER={MODELO_SMOKE} ==")
    print(f"  menciones por tipo: {dict(por_tipo)}")
    print(f"  enlazadas a la familia/orgs: {dict(canon)}")
    print(f"  PER detectadas sin enlazar (otras personas): {sin_enlazar_per}")

    # --- muestra: primeros 3 documentos anotados ---
    print("== MUESTRA (3 primeros documentos) ==")
    for d in anotados[:3]:
        print(f"\n  [{d.doc_id}]  {d.fuente}  {d.fecha_pub}")
        print(f"  texto: {d.texto[:200]}{'…' if len(d.texto) > 200 else ''}")
        if d.entidades:
            ents = ", ".join(
                f"{e.texto}→{e.entidad_id or e.tipo}" for e in d.entidades[:8]
            )
            print(f"  entidades: {ents}")


if __name__ == "__main__":
    main()
