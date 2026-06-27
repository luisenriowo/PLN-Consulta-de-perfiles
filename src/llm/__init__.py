"""Capa LLM agnóstica de proveedor.

Punto de entrada único: `get_provider()` devuelve el proveedor configurado
en el entorno (RELATIONS_LLM_PROVIDER). El resto del código de negocio
depende del protocolo `LLMProvider`, nunca de un SDK concreto.

Proveedores disponibles: anthropic | openai | groq | gemini

Para agregar un proveedor nuevo:
  1. Crear src/llm/<nombre>.py implementando LLMProvider.
  2. Registrarlo en src/llm/_config.py (_DEFAULTS, KEY_VAR, _build_provider).
  No hay que tocar nada más.
"""

from src.llm._config import get_generation_provider, get_provider
from src.llm.provider import LLMProvider

__all__ = ["get_provider", "get_generation_provider", "LLMProvider"]
