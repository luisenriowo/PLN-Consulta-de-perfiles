"""Implementación Anthropic (Claude) del protocolo LLMProvider.

`complete_json` usa tool use con tool_choice forzado: el modelo DEBE llamar
la herramienta y devolver JSON válido contra el schema — no puede responder
en texto libre. Es la forma más robusta de output estructurado en la API de
Anthropic (no existe JSON mode nativo como en OpenAI).

El cliente se instancia de forma perezosa (cached_property) para no importar
el SDK en módulos que solo usan el protocolo.
"""

from __future__ import annotations

from functools import cached_property
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_PRECIO_IN  = 1.0 / 1_000_000   # USD por token de entrada  (Haiku 4.5)
_PRECIO_OUT = 5.0 / 1_000_000   # USD por token de salida


class AnthropicProvider:
    """Cliente Claude con soporte de texto libre y output estructurado."""

    def __init__(self, *, model: str = "claude-haiku-4-5", temperature: float = 0.0) -> None:
        self.model       = model
        self._temperature = temperature
        self._usage      = {"input": 0, "output": 0, "llamadas": 0}

    @cached_property
    def _client(self):
        import anthropic
        return anthropic.Anthropic()

    # ── interfaz pública ───────────────────────────────────────────────────

    def complete(self, system: str, user: str, *, max_tokens: int = 512) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        self._track(resp.usage)
        return next((b.text for b in resp.content if b.type == "text"), "").strip()

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int = 512,
    ) -> T:
        """Output estructurado vía tool use forzado — garantiza JSON válido."""
        tool = {
            "name": "structured_output",
            "description": "Devuelve el resultado en el formato solicitado.",
            "input_schema": schema.model_json_schema(),
        }
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "structured_output"},
        )
        self._track(resp.usage)
        for block in resp.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise RuntimeError(
            "AnthropicProvider.complete_json: no se recibió bloque tool_use. "
            f"Modelo: {self.model}"
        )

    # ── telemetría ─────────────────────────────────────────────────────────

    def _track(self, usage) -> None:
        self._usage["input"]   += usage.input_tokens
        self._usage["output"]  += usage.output_tokens
        self._usage["llamadas"] += 1

    def costo(self) -> dict:
        usd = (
            self._usage["input"]  * _PRECIO_IN +
            self._usage["output"] * _PRECIO_OUT
        )
        return {**self._usage, "modelo": self.model, "usd_aprox": round(usd, 4)}
