"""Cliente LLM para condiciones abstractivas (SistemaRAG, Ablación).

Delega al LLMProvider configurado en src/llm/_config.py — mismo proveedor
que el clasificador de relaciones. Cambiar de proveedor (anthropic→groq,
groq→openai, etc.) es solo cambiar RELATIONS_LLM_PROVIDER en el .env;
cero cambios de código aquí ni en sistema_rag.py / ablacion.py.

Variables de entorno relevantes:
  RELATIONS_LLM_PROVIDER   — anthropic | groq | openai (default: anthropic)
  TIMELINE_LLM_MODEL       — modelo para generación (default del proveedor)
  TIMELINE_LLM_TEMPERATURE — float, default 0.7 (§5: variabilidad entre corridas)
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.llm._config import KEY_VAR, _PROVIDER

_key_var = KEY_VAR.get(_PROVIDER, "ANTHROPIC_API_KEY")


def disponible() -> bool:
    """True si el proveedor configurado tiene API key en el entorno."""
    return bool(os.environ.get(_key_var))


def completar(system: str, user: str, *, max_tokens: int = 320) -> str:
    """Llama al proveedor configurado y devuelve el texto generado."""
    from src.llm._config import get_generation_provider
    return get_generation_provider().complete(system, user, max_tokens=max_tokens)


def costo() -> dict:
    """Resumen de uso acumulado por el proveedor de generación."""
    from src.llm._config import get_generation_provider
    return get_generation_provider().costo()
