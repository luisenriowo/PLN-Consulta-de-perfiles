"""Implementación Groq del protocolo LLMProvider.

Groq expone una API compatible con OpenAI. `complete_json` usa JSON mode
(`response_format={"type": "json_object"}`) e inyecta el schema en el
system prompt para guiar la estructura — Groq no soporta Structured Outputs
nativos con schema Pydantic, pero con JSON mode + instrucción explícita la
tasa de cumplimiento es alta para modelos Llama 3.x.

Instalar SDK: pip install groq>=0.11
Variable de entorno requerida: GROQ_API_KEY
"""

from __future__ import annotations

import json
import time
from functools import cached_property
from threading import Lock
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


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


# Groq free tier: 30 RPM para llama-3.3-70b. Usamos 25 para margen.
_groq_limiter = _RateLimiter(25)


class GroqProvider:
    """Cliente Groq — JSON mode para output estructurado."""

    def __init__(
        self, *, model: str = "llama-3.3-70b-versatile", temperature: float = 0.0
    ) -> None:
        self.model        = model
        self._temperature = temperature
        self._usage       = {"input": 0, "output": 0, "llamadas": 0}

    @cached_property
    def _client(self):
        from groq import Groq
        # max_retries=0: el SDK no reintenta en 429 — el llamador decide
        # qué hacer (classify_grupo usa fallback a reglas).
        return Groq(max_retries=0)

    def complete(self, system: str, user: str, *, max_tokens: int = 512) -> str:
        _groq_limiter.acquire()
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
        _groq_limiter.acquire()
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
                "GroqProvider.complete_json: respuesta no válida contra el schema. "
                f"Modelo: {self.model}. Respuesta: {raw[:200]!r}"
            ) from exc

    def _track(self, usage) -> None:
        self._usage["input"]    += usage.prompt_tokens
        self._usage["output"]   += usage.completion_tokens
        self._usage["llamadas"] += 1

    def costo(self) -> dict:
        return {**self._usage, "modelo": self.model}
