"""Implementación Google Gemini del protocolo LLMProvider.

Usa el endpoint OpenAI-compatible de Google (`/v1beta/openai/`) con el SDK
`openai`, por lo que no requiere ningún SDK propietario de Google.

Free tier (AI Studio): 1 500 RPD, 1 000 000 TPD, 15 RPM.
Usamos 12 RPM para tener margen.

Variables de entorno requeridas:
  GEMINI_API_KEY — clave obtenida en https://aistudio.google.com/

SDK: openai (incluido en pyproject.toml, se instala con `uv sync`)
"""

from __future__ import annotations

import json
import time
from functools import cached_property
from threading import Lock
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_DEFAULT_MODEL = "gemini-flash-latest"


class _RateLimiter:
    """Limita llamadas a N por minuto. Thread-safe."""

    def __init__(self, calls_per_minute: int) -> None:
        self._interval = 60.0 / calls_per_minute
        self._last     = 0.0
        self._lock     = Lock()

    def acquire(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self._interval:
                time.sleep(self._interval - elapsed)
            self._last = time.monotonic()


# Gemini 2.0 Flash free tier: 15 RPM, 1500 RPD. Usamos 14 para margen.
_gemini_limiter = _RateLimiter(14)


class GeminiProvider:
    """Cliente Gemini vía endpoint OpenAI-compatible — JSON mode para output estructurado."""

    def __init__(
        self, *, model: str = _DEFAULT_MODEL, temperature: float = 0.0
    ) -> None:
        self.model        = model
        self._temperature = temperature
        self._usage       = {"input": 0, "output": 0, "llamadas": 0}

    @cached_property
    def _client(self):
        import os
        from openai import OpenAI
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY no está configurado en el entorno. "
                "Obtén una clave en https://aistudio.google.com/"
            )
        return OpenAI(api_key=api_key, base_url=_BASE_URL, max_retries=0)

    def complete(self, system: str, user: str, *, max_tokens: int = 512) -> str:
        _gemini_limiter.acquire()
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
        schema_str = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_con_schema = (
            f"{system}\n\n"
            f"Devuelve ÚNICAMENTE JSON válido que satisfaga exactamente este schema:\n"
            f"{schema_str}"
        )
        _gemini_limiter.acquire()
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_con_schema},
                {"role": "user",   "content": user},
            ],
        )
        self._track(resp.usage)
        raw = (resp.choices[0].message.content or "").strip()
        try:
            return schema.model_validate_json(raw)
        except Exception as exc:
            raise RuntimeError(
                "GeminiProvider.complete_json: respuesta no válida contra el schema. "
                f"Modelo: {self.model}. Respuesta: {raw[:200]!r}"
            ) from exc

    def _track(self, usage) -> None:
        if usage is None:
            return
        self._usage["input"]    += getattr(usage, "prompt_tokens", 0)
        self._usage["output"]   += getattr(usage, "completion_tokens", 0)
        self._usage["llamadas"] += 1

    def costo(self) -> dict:
        return {**self._usage, "modelo": self.model}
