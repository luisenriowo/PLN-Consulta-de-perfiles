"""Evaluación — Corrida del experimento (CLAUDE.md §7, §8).

Ejecuta las 4 condiciones × N corridas (N≥3, §2.5) sobre los MISMOS eventos
salientes y el gold congelado; calcula Date F1, ROUGE por alineamiento y tasa
de alucinación por corrida, y agrega media ± desviación estándar por condición.
Loguea el costo de LLM (§4, §10).

Requiere el GOLD CONGELADO en `annotation/gold/` (CSV con columnas de
protocol.md §4: fecha, descripcion, fuentes, …). Mientras no exista, este script
avisa y no corre (el arnés de métricas se valida aparte con scripts/test_eval.py).

Uso:  python -m eval.run_experiment [N]
"""

from __future__ import annotations

import statistics
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from eval import metrics
from src.generation import _llm
from src.generation.ablacion import Ablacion
from src.generation.b0_lead import B0Lead
from src.generation.b1_extractive import B1Extractive
from src.generation.base import GenerationCondition
from src.generation.sistema_rag import SistemaRAG
from src.pipeline import cluster, salience
from src.schemas import Documento, TimelineEntry

CORPUS = Path("data/corpus_humala.parquet")
GOLD_DIR = Path("annotation/gold")
TOL_DIAS = 1  # fecha_normalizada es proxy de pub; tolera ±1 día vs evento


def cargar_gold() -> list[TimelineEntry]:
    """Lee el gold congelado (CSV protocol.md §4) como TimelineEntry."""
    csvs = sorted(GOLD_DIR.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(
            f"No hay gold congelado en {GOLD_DIR}/. El arnés está listo; "
            "espera a que los humanos congelen el gold (ver annotation/protocol.md)."
        )
    df = pd.read_csv(csvs[0])
    return [
        TimelineEntry(
            fecha=date.fromisoformat(str(r["fecha"])),
            resumen=str(r["descripcion"]),
            fuentes=[s for s in str(r["fuentes"]).split(",") if s],
        )
        for r in df.to_dict(orient="records")
    ]


def mapa_fuentes() -> dict[str, str]:
    df = pd.read_parquet(CORPUS, columns=["doc_id", "texto"])
    return dict(zip(df["doc_id"], df["texto"]))


def eventos_salientes() -> list:
    df = pd.read_parquet(CORPUS)
    df = df[df["humala_protagonista"]]
    docs = [
        Documento(
            doc_id=r["doc_id"],
            fuente=r["fuente"],
            url=r["url"],
            fecha_pub=date.fromisoformat(r["fecha_pub"]),
            texto=r["texto"],
        )
        for r in df.to_dict(orient="records")
    ]
    return salience.select_salient(
        cluster.cluster_events(docs, umbral=cluster.UMBRAL_DEFECTO),
        sujeto_patron=salience.patron_sujeto(["Humala", "Ollanta"]),
    )


def _media_desv(xs: list[float]) -> tuple[float, float]:
    return (statistics.mean(xs), statistics.stdev(xs) if len(xs) > 1 else 0.0)


def run_experiment(n: int = 3) -> None:
    gold = cargar_gold()
    fuentes = mapa_fuentes()
    clusters = eventos_salientes()
    print(
        f"gold={len(gold)}  eventos_salientes={len(clusters)}  N={n}  tol={TOL_DIAS}d"
    )

    condiciones: list[GenerationCondition] = [B0Lead(), B1Extractive()]
    if _llm.disponible():
        condiciones += [SistemaRAG(), Ablacion()]
    else:
        print("⚠ Sin ANTHROPIC_API_KEY: solo se evalúan B0/B1.")

    print(f"\n{'condición':<16}{'Date F1':>16}{'ROUGE-1':>16}{'Aluc.':>16}{'n':>6}")
    resultados = {}
    for cond in condiciones:
        df1, r1, al, ne = [], [], [], []
        for _ in range(n):
            pred = cond.generate(clusters)
            df1.append(metrics.date_f1(pred, gold, tol_dias=TOL_DIAS)["f1"])
            r1.append(metrics.rouge_vs_gold(pred, gold, tol_dias=TOL_DIAS)["rouge1"])
            al.append(metrics.tasa_alucinacion(pred, fuentes)["tasa"])
            ne.append(len(pred))
        resultados[cond.name] = {
            "date_f1": _media_desv(df1),
            "rouge1": _media_desv(r1),
            "aluc": _media_desv(al),
            "n": statistics.mean(ne),
        }
        m = resultados[cond.name]
        print(
            f"{cond.name:<16}"
            f"{m['date_f1'][0]:>8.3f}±{m['date_f1'][1]:<6.3f}"
            f"{m['rouge1'][0]:>8.3f}±{m['rouge1'][1]:<6.3f}"
            f"{m['aluc'][0]:>8.3f}±{m['aluc'][1]:<6.3f}"
            f"{m['n']:>6.0f}"
        )

    if _llm.disponible():
        print(f"\ncosto LLM: {_llm.costo()}")
    print(
        "\n⚠ La tasa de alucinación es por el juez NLI: valídalo con "
        "eval.nli.validar_juez sobre un subconjunto humano antes de reportarla."
    )


if __name__ == "__main__":
    try:
        run_experiment(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
    except FileNotFoundError as e:
        print(e)
