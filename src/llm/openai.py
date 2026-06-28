"""Implementación OpenAI del protocolo LLMProvider.

`complete_json` usa Structured Outputs (beta.chat.completions.parse) con
el schema Pydantic directamente — OpenAI garantiza JSON válido y tipado.
Requiere modelos que soporten Structured Outputs (gpt-4o-mini en adelante).

SDK: openai (incluido en pyproject.toml, se instala con `uv sync`)
Variable de entorno requerida: OPENAI_API_KEY
"""

from __future__ import annotations

from functools import cached_property
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    """Cliente OpenAI con texto libre y Structured Outputs."""

    def __init__(self, *, model: str = "gpt-4o-mini", temperature: float = 0.0) -> None:
        self.model        = model
        self._temperature = temperature
        self._usage       = {"input": 0, "output": 0, "llamadas": 0}

    @cached_property
    def _client(self):
        from openai import OpenAI
        return OpenAI()

    def complete(self, system: str, user: str, *, max_tokens: int = 512) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        self._track(resp.usage)
        return (resp.choices[0].message.content or "").strip()

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int = 512,
    ) -> T:
        resp = self._client.beta.chat.completions.parse(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            response_format=schema,
        )
        self._track(resp.usage)
        parsed = resp.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError(
                "OpenAIProvider.complete_json: respuesta sin output estructurado. "
                f"Modelo: {self.model}"
            )
        return parsed

    def _track(self, usage) -> None:
        self._usage["input"]    += usage.prompt_tokens
        self._usage["output"]   += usage.completion_tokens
        self._usage["llamadas"] += 1

    def costo(self) -> dict:
        return {**self._usage, "modelo": self.model}
