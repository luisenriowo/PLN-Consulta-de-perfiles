"""Cliente LLM compartido por las condiciones abstractivas (Sistema, Ablación).

Usa el SDK oficial `anthropic`. La key se resuelve del entorno
(`ANTHROPIC_API_KEY`), cargada desde un `.env` gitignored si existe — nunca
hardcodeada. Modelo barato en desarrollo (CLAUDE.md §4); se fija `temperature`
(§5). La API de Anthropic NO tiene parámetro `seed`: la variación entre las N
corridas (§2.5) viene de la no-determinación natural del modelo.

Loguea el costo acumulado de LLM (§4, §10).
"""

from __future__ import annotations

import functools
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Modelo barato para desarrollo; cambiar a uno más capaz para la corrida final
# de evaluación vía la variable de entorno TIMELINE_LLM_MODEL.
MODELO = os.environ.get("TIMELINE_LLM_MODEL", "claude-haiku-4-5")
TEMPERATURA = 0.7   # fija (§5); Haiku 4.5 sí acepta temperature

# Precio Haiku 4.5 (USD por 1M tokens): entrada $1, salida $5.
_PRECIO_IN, _PRECIO_OUT = 1.0 / 1e6, 5.0 / 1e6
_acumulado = {"input": 0, "output": 0, "llamadas": 0}


def disponible() -> bool:
    """True si hay API key en el entorno (sin instanciar el cliente)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@functools.lru_cache(maxsize=1)
def _cliente():
    import anthropic

    return anthropic.Anthropic()   # lee ANTHROPIC_API_KEY del entorno


def completar(system: str, user: str, *, max_tokens: int = 320) -> str:
    """Una llamada a Claude; devuelve el texto y acumula el costo."""
    resp = _cliente().messages.create(
        model=MODELO,
        max_tokens=max_tokens,
        temperature=TEMPERATURA,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    _acumulado["input"] += resp.usage.input_tokens
    _acumulado["output"] += resp.usage.output_tokens
    _acumulado["llamadas"] += 1
    return next((b.text for b in resp.content if b.type == "text"), "").strip()


def costo() -> dict:
    """Resumen de uso/costo de LLM acumulado en el proceso."""
    usd = _acumulado["input"] * _PRECIO_IN + _acumulado["output"] * _PRECIO_OUT
    return {**_acumulado, "modelo": MODELO, "usd_aprox": round(usd, 4)}
