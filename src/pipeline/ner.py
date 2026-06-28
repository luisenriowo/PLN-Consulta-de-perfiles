"""Protocolo NERModel e implementaciones intercambiables (SOLID: O, L, D).

Dos implementaciones listas para usar:
  SpacyNER       — es_core_news_lg. Ligero, ideal para dev y smoke tests.
  TransformerNER — bert-spanish-cased-finetuned-ner (mrm8488, CoNLL-2002 ES).
                   Entrenado sobre noticias; ventanea por oraciones (tope 512 tok).

Selección por variable de entorno:
  NER_MODEL=spacy        → SpacyNER  (default)
  NER_MODEL=transformer  → TransformerNER

Para agregar un modelo nuevo basta implementar NERModel y registrarlo en
get_ner_model(). No hay que tocar SpacyNER ni TransformerNER.
"""

from __future__ import annotations

import os
import re
from functools import cached_property, lru_cache
from typing import Protocol, runtime_checkable

from src.schemas import EntidadMencion

_TIPOS_VALIDOS = {"PER", "ORG", "LOC", "MISC"}
# Separador de oraciones (cierre + espacio) para ventanear sin partir entidades.
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")


# ── Protocolo ─────────────────────────────────────────────────────────────────


@runtime_checkable
class NERModel(Protocol):
    """Contrato mínimo de un modelo NER: recibe textos, devuelve menciones."""

    def __call__(self, texts: list[str]) -> list[list[EntidadMencion]]:
        """Procesa una lista de textos en batch y devuelve las menciones por texto."""
        ...


# ── SpacyNER ──────────────────────────────────────────────────────────────────


class SpacyNER:
    """NER con spaCy es_core_news_lg. Rápido, sin dependencia de GPU."""

    def __init__(self, model: str = "es_core_news_lg") -> None:
        self._model_name = model

    @cached_property
    def _nlp(self):
        import spacy

        return spacy.load(
            self._model_name,
            disable=["lemmatizer", "morphologizer", "tagger"],
        )

    def __call__(self, texts: list[str]) -> list[list[EntidadMencion]]:
        resultado: list[list[EntidadMencion]] = []
        for doc in self._nlp.pipe(texts, batch_size=32):
            menciones = [
                EntidadMencion(
                    texto=ent.text,
                    tipo=ent.label_,
                    inicio=ent.start_char,
                    fin=ent.end_char,
                )
                for ent in doc.ents
                if ent.label_ in _TIPOS_VALIDOS
            ]
            resultado.append(menciones)
        return resultado


# ── TransformerNER ────────────────────────────────────────────────────────────


class TransformerNER:
    """NER con bert-spanish-cased-finetuned-ner (mrm8488) — BETO afinado en
    CoNLL-2002 español (dominio noticias). Etiquetas PER/ORG/LOC/MISC.

    Usa aggregation_strategy="simple" para reconstruir spans completos desde
    sub-tokens. Como BERT topa en 512 tokens, ventanea el texto en LÍMITES DE
    ORACIÓN (las entidades nunca cruzan oraciones). Corre en CPU por defecto;
    device=0 para GPU.
    """

    # Mapeo etiquetas del modelo → etiquetas internas del proyecto.
    # CoNLL-2002 usa PER/ORG/LOC/MISC; OTH (otros esquemas) → MISC.
    _LABEL_MAP: dict[str, str] = {
        "PER": "PER",
        "PERSON": "PER",
        "ORG": "ORG",
        "ORGANIZATION": "ORG",
        "LOC": "LOC",
        "LOCATION": "LOC",
        "MISC": "MISC",
        "OTH": "MISC",
    }

    # Ventanas de oraciones empacadas hasta _MAXCHARS chars. 800 ≈ <512 tokens
    # incluso en texto denso (tablas de cifras), evitando el tope de posición.
    _MAXCHARS = 800

    def __init__(
        self,
        model: str = "mrm8488/bert-spanish-cased-finetuned-ner",
        *,
        device: int = -1,
        batch_size: int = 16,
    ) -> None:
        self._model_name = model
        self._device = device
        self._batch_size = batch_size

    @cached_property
    def _pipe(self):
        from transformers import pipeline

        return pipeline(  # ty: ignore[no-matching-overload]
            "ner",
            model=self._model_name,
            aggregation_strategy="simple",
            device=self._device,
        )

    def _ventanas(self, t: str) -> list[tuple[str, int]]:
        """Parte `t` en ventanas (subtexto, offset_base) ≤ _MAXCHARS empacando
        oraciones completas. Solo char-corta si una oración sola excede el límite."""
        spans, cursor = [], 0
        for sent in _SENT_SPLIT.split(t):
            if not sent.strip():
                continue
            pos = t.find(sent, cursor)
            if pos < 0:
                pos = cursor
            spans.append((pos, pos + len(sent)))
            cursor = pos + len(sent)
        if not spans:
            spans = [(0, len(t))]

        out: list[tuple[str, int]] = []
        i = 0
        while i < len(spans):
            ini, fin, j = spans[i][0], spans[i][1], i + 1
            while j < len(spans) and spans[j][1] - ini <= self._MAXCHARS:
                fin, j = spans[j][1], j + 1
            if fin - ini <= self._MAXCHARS:
                out.append((t[ini:fin], ini))
            else:                                  # oración única demasiado larga
                s = ini
                while s < fin:
                    e = min(s + self._MAXCHARS, fin)
                    if e < fin:
                        c = t.rfind(" ", s + self._MAXCHARS // 2, e)
                        if c > s:
                            e = c
                    out.append((t[s:e], s))
                    s = e if e > s else fin
            i = j
        return out

    def __call__(self, texts: list[str]) -> list[list[EntidadMencion]]:
        if not texts:
            return []
        # Ventanear por oraciones para no exceder los 512 tokens del modelo;
        # se guarda el offset base de cada ventana para situar la mención.
        subtextos: list[str] = []
        mapa: list[tuple[int, int]] = []   # (idx_texto, offset_base)
        for ti, t in enumerate(texts):
            t = t or ""
            if not t:
                subtextos.append("")
                mapa.append((ti, 0))
                continue
            for sub, base in self._ventanas(t):
                subtextos.append(sub)
                mapa.append((ti, base))

        raw_all: list = self._pipe(subtextos, batch_size=self._batch_size)

        # Dedup por (inicio, fin); descartar fragmentos subword residuales.
        por_texto: list[dict[tuple[int, int], EntidadMencion]] = [{} for _ in texts]
        for raw, (ti, base) in zip(raw_all, mapa):
            for ent in raw:
                tipo = self._LABEL_MAP.get(ent["entity_group"], "MISC")
                if tipo not in _TIPOS_VALIDOS:
                    continue
                texto = ent["word"].replace("##", "").strip()
                if len(texto) < 2 or texto.startswith("#"):
                    continue
                ini, fin = ent["start"] + base, ent["end"] + base
                por_texto[ti][(ini, fin)] = EntidadMencion(
                    texto=texto, tipo=tipo, inicio=ini, fin=fin,
                )
        return [list(d.values()) for d in por_texto]


# ── Factory ───────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_ner_model() -> NERModel:
    """Devuelve el modelo NER configurado. Singleton por proceso.

    Variables de entorno:
      NER_MODEL             — "spacy" (default) | "transformer"
      SPACY_NER_MODEL       — modelo spaCy (default: es_core_news_lg)
      TRANSFORMER_NER_MODEL — modelo HuggingFace (default: mrm8488/bert-spanish-cased-finetuned-ner)
    """
    choice = os.environ.get("NER_MODEL", "spacy").lower()
    if choice == "transformer":
        model = os.environ.get(
            "TRANSFORMER_NER_MODEL", "mrm8488/bert-spanish-cased-finetuned-ner"
        )
        return TransformerNER(model=model, device=_ner_device())
    model = os.environ.get("SPACY_NER_MODEL", "es_core_news_lg")
    return SpacyNER(model=model)


def _ner_device() -> int:
    """Device para TransformerNER: NER_DEVICE si está, si no auto (GPU si hay CUDA).

    `0` = primera GPU, `-1` = CPU. Auto-detecta CUDA para no quedarse en CPU por
    accidente cuando hay GPU disponible (clave para el run a escala).
    """
    env = os.environ.get("NER_DEVICE")
    if env is not None:
        return int(env)
    try:
        import torch
        return 0 if torch.cuda.is_available() else -1
    except Exception:
        return -1
