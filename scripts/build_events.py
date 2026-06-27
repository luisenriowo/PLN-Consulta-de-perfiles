"""Clusteriza el corpus protagonista en eventos y reporta el conteo.

Responde la pregunta-gate que quedó abierta: ¿cuántos EVENTOS distintos cubre el
corpus? (<~30 = línea de tiempo flaca). Muestra sensibilidad al umbral para
calibrar, y persiste los eventos del umbral elegido.

Uso:  python scripts/build_events.py [umbral]
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

from src.pipeline import cluster, salience
from src.schemas import Documento

CORPUS = Path("data/corpus_humala.parquet")
SALIDA = Path("data/eventos_humala.parquet")
UMBRAL = float(sys.argv[1]) if len(sys.argv) > 1 else cluster.UMBRAL_DEFECTO


def cargar_protagonistas() -> list[Documento]:
    df = pd.read_parquet(CORPUS)
    df = df[df["humala_protagonista"]]
    return [
        Documento(
            doc_id=r.doc_id,
            fuente=r.fuente,
            url=r.url,
            fecha_pub=date.fromisoformat(r.fecha_pub),
            texto=r.texto,
        )
        for r in df.itertuples()
    ]


def main() -> None:
    docs = cargar_protagonistas()
    print(f"Corpus protagonista: {len(docs)} docs")

    print("\n== SENSIBILIDAD AL UMBRAL (distancia coseno) ==")
    for u in (0.25, 0.30, 0.35, 0.40, 0.45):
        evs = cluster.cluster_events(docs, umbral=u)
        multi = sum(1 for e in evs if len(e.fuentes) >= 2)
        print(f"  umbral {u:.2f}: {len(evs):3d} eventos  ({multi} con ≥2 notas)")

    print(f"\n== EVENTOS con umbral={UMBRAL} ==")
    eventos = cluster.cluster_events(docs, umbral=UMBRAL)
    tam = Counter(len(e.fuentes) for e in eventos)
    multi = [e for e in eventos if len(e.fuentes) >= 2]
    print(f"  total eventos: {len(eventos)}")
    print(f"  singletons (1 nota): {tam.get(1, 0)}  | multi-nota (≥2): {len(multi)}")
    anios = Counter(e.fecha_normalizada.year for e in eventos)
    print(f"  eventos por año: {dict(sorted(anios.items()))}")

    print("\n== SALIENCE (§2: saliente si ≥2 señales) ==")
    patron = salience.patron_sujeto(["Humala", "Ollanta"])
    salientes = salience.select_salient(eventos, sujeto_patron=patron)
    conteo_senal = Counter()
    for e in eventos:
        for s, v in salience.senales(e, sujeto_patron=patron).items():
            if v:
                conteo_senal[s] += 1
    print(f"  eventos salientes: {len(salientes)} de {len(eventos)}")
    print(f"  frecuencia de señales: {dict(conteo_senal)}")
    sal_ids = {e.cluster_id for e in salientes}
    anios_sal = Counter(e.fecha_normalizada.year for e in salientes)
    print(f"  salientes por año: {dict(sorted(anios_sal.items()))}")

    print("\n== LÍNEA DE TIEMPO SALIENTE (cronológica) ==")
    for e in salientes:
        ss = "+".join(k for k, v in salience.senales(e, sujeto_patron=patron).items() if v)
        print(f"  {e.fecha_normalizada} [{len(e.fuentes):2d}n] {e.pasajes_evidencia[0][:72]}  ({ss})")

    filas = [{
        "cluster_id": e.cluster_id,
        "fecha_normalizada": e.fecha_normalizada.isoformat(),
        "n_notas": len(e.fuentes),
        "n_fechas": len(set(e.fechas_evidencia)),
        "saliente": e.cluster_id in sal_ids,
        "senales": "+".join(k for k, v in salience.senales(e, sujeto_patron=patron).items() if v),
        "fuentes": ",".join(e.fuentes),
        "pasaje_representativo": e.pasajes_evidencia[0] if e.pasajes_evidencia else "",
    } for e in eventos]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).to_parquet(SALIDA, index=False)
    print(f"\n== PERSISTIDO ==\n  {SALIDA} ({len(filas)} eventos, {len(salientes)} salientes)")


if __name__ == "__main__":
    main()
