"""Evaluación — Juez de respaldo por NLI/entailment en español (CLAUDE.md §7).

Decide si el `resumen` de una entrada está RESPALDADO por el texto de sus
fuentes: cada oración del resumen debe estar *implicada* (entailment) por la
premisa (texto fuente). Modelo NLI multilingüe (mDeBERTa mnli-xnli).

⚠ La tasa de alucinación es la métrica ESTRELLA del informe: NO se reporta el
número titular desde este juez automático sin validarlo. `validar_juez` compara
los veredictos del NLI contra un subconjunto etiquetado a mano y devuelve su
acierto (sobre todo el recall en la clase 'no respaldado'). Validar antes de
reportar.
"""

from __future__ import annotations

import functools

from src.pipeline.preprocess import segmentar_oraciones

MODELO_NLI = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
UMBRAL_ENTAILMENT = 0.5   # prob mínima de entailment para considerar respaldada


@functools.lru_cache(maxsize=1)
def _modelo():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODELO_NLI)
    mod = AutoModelForSequenceClassification.from_pretrained(MODELO_NLI)
    mod.eval()
    id2label = {i: v.lower() for i, v in mod.config.id2label.items()}
    return tok, mod, id2label, torch


def _probs(premisa: str, hipotesis: str) -> dict[str, float]:
    """Probabilidades NLI {entailment, neutral, contradiction}."""
    tok, mod, id2label, torch = _modelo()
    entradas = tok(
        premisa, hipotesis, truncation="only_first", max_length=512, return_tensors="pt"
    )
    with torch.no_grad():
        logits = mod(**entradas).logits[0]
    probs = torch.softmax(logits, dim=-1).tolist()
    return {id2label[i]: probs[i] for i in range(len(probs))}


def respaldado(resumen: str, premisa: str, *, umbral: float = UMBRAL_ENTAILMENT) -> bool:
    """True si TODA oración del resumen está implicada por la premisa."""
    if not premisa.strip():
        return False
    oraciones = segmentar_oraciones(resumen) or [resumen]
    return all(_probs(premisa, o).get("entailment", 0.0) >= umbral for o in oraciones)


def validar_juez(
    entries,
    fuentes_texto: dict[str, str],
    etiquetas_manual: dict[int, bool],
    *,
    umbral: float = UMBRAL_ENTAILMENT,
) -> dict:
    """Compara el juez NLI vs etiquetas humanas (True = respaldado) en un subconjunto.

    `etiquetas_manual`: índice de entrada -> respaldo manual. Devuelve acierto
    global y, clave para alucinación, el recall sobre la clase 'no respaldado'.
    """
    aciertos = 0
    # matriz de confusión sobre la clase "NO respaldado" (= alucinación)
    vp = vn = fp = fn = 0
    for i, manual in etiquetas_manual.items():
        e = entries[i]
        premisa = "\n".join(fuentes_texto.get(f, "") for f in e.fuentes).strip()
        juez = respaldado(e.resumen, premisa, umbral=umbral)
        aciertos += int(juez == manual)
        # positivo = alucinación (no respaldado)
        if not manual and not juez:
            vp += 1
        elif manual and juez:
            vn += 1
        elif manual and not juez:
            fp += 1
        else:
            fn += 1
    n = len(etiquetas_manual)
    rec_aluc = vp / (vp + fn) if (vp + fn) else 0.0
    prec_aluc = vp / (vp + fp) if (vp + fp) else 0.0
    return {
        "n": n,
        "acierto": aciertos / n if n else 0.0,
        "alucinacion_precision": prec_aluc,
        "alucinacion_recall": rec_aluc,
        "matriz": {"vp": vp, "vn": vn, "fp": fp, "fn": fn},
    }
