"""Protocolo NERModel e implementaciones intercambiables (SOLID: O, L, D).

Dos implementaciones listas para usar:
  SpacyNER       — es_core_news_lg. Ligero, ideal para dev y smoke tests.
  TransformerNER — roberta-base-bne-capiter (PlanTL). Entrenado sobre noticias
                   en español; mejor precisión para texto político peruano.

Selección por variable de entorno:
  NER_MODEL=spacy        → SpacyNER  (default)
  NER_MODEL=transformer  → TransformerNER

Para agregar un modelo nuevo basta implementar NERModel y registrarlo en
get_ner_model(). No hay que tocar SpacyNER ni TransformerNER.
"""

from __future__ import annotations

import os
from functools import cached_property, lru_cache
from typing import Protocol, runtime_checkable

from src.schemas import EntidadMencion

_TIPOS_VALIDOS = {"PER", "ORG", "LOC", "MISC"}


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
    """NER con roberta-base-bne-capiter — mejor precisión para noticias en español.

    Usa aggregation_strategy="simple" para reconstruir spans completos desde
    sub-tokens (evita menciones fragmentadas como "Castill" + "##o").
    Corre en CPU por defecto; cambiar device=0 para GPU.
    """

    # Mapeo etiquetas del modelo → etiquetas internas del proyecto
    _LABEL_MAP: dict[str, str] = {
        "PER": "PER",
        "PERSON": "PER",
        "ORG": "ORG",
        "ORGANIZATION": "ORG",
        "LOC": "LOC",
        "LOCATION": "LOC",
        "MISC": "MISC",
    }

    def __init__(
        self,
        model: str = "PlanTL-GOB-ES/roberta-base-bne-capiter",
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

    def __call__(self, texts: list[str]) -> list[list[EntidadMencion]]:
        if not texts:
            return []
        # La pipeline de transformers hace batching interno cuando recibe lista.
        # Devuelve list[list[dict]] cuando la entrada es list[str].
        raw_all: list = self._pipe(texts, batch_size=self._batch_size)
        resultado: list[list[EntidadMencion]] = []
        for raw in raw_all:
            menciones = []
            for ent in raw:
                tipo = self._LABEL_MAP.get(ent["entity_group"], "MISC")
                if tipo not in _TIPOS_VALIDOS:
                    continue
                menciones.append(
                    EntidadMencion(
                        texto=ent["word"].strip(),
                        tipo=tipo,
                        inicio=ent["start"],
                        fin=ent["end"],
                    )
                )
            resultado.append(menciones)
        return resultado


# ── Factory ───────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_ner_model() -> NERModel:
    """Devuelve el modelo NER configurado. Singleton por proceso.

    Variables de entorno:
      NER_MODEL             — "spacy" (default) | "transformer"
      SPACY_NER_MODEL       — modelo spaCy (default: es_core_news_lg)
      TRANSFORMER_NER_MODEL — modelo HuggingFace (default: PlanTL-GOB-ES/roberta-base-bne-capiter)
    """
    choice = os.environ.get("NER_MODEL", "spacy").lower()
    if choice == "transformer":
        model = os.environ.get(
            "TRANSFORMER_NER_MODEL", "PlanTL-GOB-ES/roberta-base-bne-capiter"
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
