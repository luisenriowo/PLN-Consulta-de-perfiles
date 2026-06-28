"""Factory de proveedores LLM — resuelve implementaciones desde el entorno.

Dos proveedores, mismo proveedor subyacente:
  get_provider()            — clasificación de relaciones (temperature=0.0)
  get_generation_provider() — generación de timeline    (temperature=0.7, §5)

Variables de entorno compartidas:
  RELATIONS_LLM_PROVIDER    — anthropic | openai | groq | gemini
                              Governa AMBOS proveedores: cambiar aquí es
                              suficiente para migrar de proveedor sin tocar código.

Variables por uso:
  RELATIONS_LLM_MODEL       — modelo para clasificación
  RELATIONS_LLM_TEMPERATURE — float, default 0.0
  TIMELINE_LLM_MODEL        — modelo para generación
  TIMELINE_LLM_TEMPERATURE  — float, default 0.7 (§5: variabilidad entre corridas)

Los proveedores se instancian una sola vez por proceso (lru_cache). Para tests
que necesiten proveedor distinto, limpiar la cache con .cache_clear().
"""

from __future__ import annotations

import os
from functools import lru_cache

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Proveedor compartido — governa tanto relaciones como generación.
_PROVIDER = os.environ.get("RELATIONS_LLM_PROVIDER", "anthropic").lower()

# Parámetros de clasificación de relaciones
_REL_MODEL = os.environ.get("RELATIONS_LLM_MODEL", "")
try:
    _REL_TEMPERATURE = float(os.environ.get("RELATIONS_LLM_TEMPERATURE", "0.0"))
except ValueError:
    _REL_TEMPERATURE = 0.0

# Parámetros de generación de timeline
_GEN_MODEL = os.environ.get("TIMELINE_LLM_MODEL", "")
try:
    _GEN_TEMPERATURE = float(os.environ.get("TIMELINE_LLM_TEMPERATURE", "0.7"))
except ValueError:
    _GEN_TEMPERATURE = 0.7

_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-flash-latest",
}

# Proveedor → nombre de la env var de su API key.
KEY_VAR: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _build_provider(model: str, temperature: float):
    if _PROVIDER == "anthropic":
        from src.llm.anthropic import AnthropicProvider

        return AnthropicProvider(model=model, temperature=temperature)
    if _PROVIDER == "openai":
        from src.llm.openai import OpenAIProvider

        return OpenAIProvider(model=model, temperature=temperature)
    if _PROVIDER == "groq":
        from src.llm.groq import GroqProvider

        return GroqProvider(model=model, temperature=temperature)
    if _PROVIDER == "gemini":
        from src.llm.gemini import GeminiProvider

        return GeminiProvider(model=model, temperature=temperature)
    raise ValueError(
        f"RELATIONS_LLM_PROVIDER={_PROVIDER!r} no reconocido. "
        "Opciones: anthropic, openai, groq, gemini."
    )


@lru_cache(maxsize=1)
def get_provider():
    """Proveedor para clasificación de relaciones (temperature=0.0). Singleton."""
    return _build_provider(
        model=_REL_MODEL or _DEFAULTS.get(_PROVIDER, ""),
        temperature=_REL_TEMPERATURE,
    )


@lru_cache(maxsize=1)
def get_generation_provider():
    """Proveedor para generación de timeline (temperature=0.7, §5). Singleton."""
    return _build_provider(
        model=_GEN_MODEL or _DEFAULTS.get(_PROVIDER, ""),
        temperature=_GEN_TEMPERATURE,
    )
