"""Contrato del proveedor LLM — agnóstico de servicio (SOLID: D).

Todo módulo que necesite un LLM depende de esta abstracción, nunca de un
SDK concreto. Cada implementación (AnthropicProvider, OpenAIProvider, etc.)
satisface este protocolo sin herencia; basta con que tenga los métodos.

`complete`      — texto libre, útil para summarización / generación.
`complete_json` — output estructurado garantizado: el LLM está obligado a
                  devolver JSON válido conforme al schema Pydantic recibido.
                  Esto elimina el parsing defensivo en los clasificadores.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    """Interfaz mínima que todo proveedor LLM debe satisfacer."""

    model: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 512,
    ) -> str:
        """Completado de texto libre. Devuelve el texto de la respuesta."""
        ...

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int = 512,
    ) -> T:
        """Completado con salida estructurada garantizada.

        Usa tool use / JSON mode según el proveedor para forzar que la
        respuesta sea JSON válido conforme al schema Pydantic `schema`.
        Lanza RuntimeError si el proveedor no devuelve output estructurado.
        """
        ...
