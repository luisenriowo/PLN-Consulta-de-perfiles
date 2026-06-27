"""Protocolo RelationClassifier e implementaciones (SOLID: O, L, D).

Tres implementaciones listas:

  RuleBasedClassifier — lexicón de verbos + triple del dep parse.
                        Sin LLM. Rápido, determinista, costo cero.
                        Confianza media: funciona en relaciones explícitas.

  LLMClassifier       — delega al LLMProvider configurado (agnóstico).
                        Alta calidad, maneja relaciones implícitas y contexto
                        político complejo. Costo por llamada.

  HybridClassifier    — RECOMENDADO. Reglas primero; si la confianza queda
                        por debajo del umbral escala al LLM. Minimiza
                        llamadas al LLM (y costo) sin sacrificar calidad
                        donde las reglas son insuficientes.

Para agregar un clasificador nuevo basta implementar RelationClassifier.
No hay que tocar las implementaciones existentes.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from src.pipeline.relations import Coocurrencia
from src.schemas import RelationResult, TIPOS_RELACION

# ── Lexicón de verbos → tipo de relación (para RuleBased) ─────────────────
# Orden importa: el primero que matchee gana.
# (patrón_regex, tipo, confianza_asignada)
_LEXICON: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\b(nombr|design|eleg|postul|candid|propus|ascend)\w*",  re.I), "nombramiento", 0.82),
    (re.compile(r"\b(acus|imput|investig|denunci|procesa|enjuici|fiscal)\w*", re.I), "acusacion",    0.82),
    (re.compile(r"\b(renunci|alej|expuls|abandon|separ|destitu|dimit)\w*", re.I), "ruptura",       0.78),
    (re.compile(r"\b(pertenec|integr|militan|afili|miembro|fundó|lider)\w*", re.I), "pertenencia",   0.78),
    (re.compile(r"\b(apoy|respald|aval|defendi|aliado|pact|sumó)\w*",    re.I), "alianza",        0.75),
    (re.compile(r"\b(rechaz|critic|enfrent|opuso|atac|cuestion|impugn)\w*", re.I), "conflicto",     0.72),
]

_CONFIANZA_MENCION = 0.40   # cuando no matchea ningún patrón


# ── Protocolo ──────────────────────────────────────────────────────────────

@runtime_checkable
class RelationClassifier(Protocol):
    """Contrato mínimo de un clasificador de relaciones."""

    def classify(self, cooc: Coocurrencia) -> RelationResult:
        """Clasifica la relación descrita en `cooc` y devuelve el resultado."""
        ...


# ── RuleBasedClassifier ────────────────────────────────────────────────────

class RuleBasedClassifier:
    """Clasificación por lexicón de verbos sobre el triple del dep parse.

    Busca primero en el verbo del triple (más preciso); si no hay triple,
    busca en la oración completa (más recall, menos precisión).
    """

    def classify(self, cooc: Coocurrencia) -> RelationResult:
        # Preferimos el verbo del triple porque es más semánticamente puro.
        texto_busqueda = cooc.triple[1] if cooc.triple else cooc.oracion

        for patron, tipo, confianza in _LEXICON:
            if patron.search(texto_busqueda):
                return RelationResult(
                    tipo=tipo, confianza=confianza,
                    evidencia=cooc.oracion, metodo="rules",
                )

        # Fallback: buscar en la oración completa si el triple no matcheó.
        if cooc.triple:
            for patron, tipo, confianza in _LEXICON:
                if patron.search(cooc.oracion):
                    return RelationResult(
                        tipo=tipo, confianza=confianza * 0.9,   # penalización leve
                        evidencia=cooc.oracion, metodo="rules",
                    )

        return RelationResult(
            tipo="mencion", confianza=_CONFIANZA_MENCION,
            evidencia=cooc.oracion, metodo="rules",
        )


# ── LLMClassifier ──────────────────────────────────────────────────────────

class _LLMOutput(BaseModel):
    """Schema del output estructurado que devuelve el LLM."""
    tipo:      str
    confianza: float   # 0.0 – 1.0
    razon:     str     # explicación breve (mejora trazabilidad y debug)


_SYSTEM_LLM = (
    "Eres un analista político especializado en política peruana. "
    "Dada una oración y dos entidades, clasifica la relación entre ellas "
    "en UNA de estas categorías: "
    + ", ".join(f"{k} ({v})" for k, v in TIPOS_RELACION.items())
    + ".\n"
    "confianza: certeza de tu clasificación (0.0 = muy incierto, 1.0 = muy seguro).\n"
    "razon: 1 oración explicando por qué elegiste ese tipo."
)


class LLMClassifier:
    """Clasificación vía el LLMProvider configurado en el entorno.

    El proveedor se instancia de forma perezosa para no requerir la API key
    en módulos que no llamen a classify().
    """

    def __init__(self) -> None:
        self._provider = None

    def _get_provider(self):
        if self._provider is None:
            from src.llm import get_provider
            self._provider = get_provider()
        return self._provider

    def classify(self, cooc: Coocurrencia) -> RelationResult:
        user = (
            f"Entidad A: {cooc.entity_a.nombre}\n"
            f"Entidad B: {cooc.entity_b.nombre}\n"
            f"Oración:   {cooc.oracion}"
        )
        out  = self._get_provider().complete_json(_SYSTEM_LLM, user, _LLMOutput)
        tipo = out.tipo if out.tipo in TIPOS_RELACION else "mencion"
        return RelationResult(
            tipo=tipo, confianza=min(max(out.confianza, 0.0), 1.0),
            evidencia=cooc.oracion, metodo="llm",
        )


# ── HybridClassifier ───────────────────────────────────────────────────────

class HybridClassifier:
    """Reglas primero; LLM solo cuando la confianza queda bajo el umbral.

    Estrategia:
      1. RuleBasedClassifier clasifica la co-ocurrencia.
      2. Si confianza >= umbral → devuelve el resultado de reglas.
      3. Si confianza <  umbral → escala al LLM y devuelve ese resultado
         marcado como método "hybrid".

    Si el LLM falla con un error de cuota/rate-limit, se desactiva para
    el resto del proceso (`_llm_desactivado = True`) y solo se usan reglas.
    """

    def __init__(self, *, umbral: float = 0.65) -> None:
        self._rules           = RuleBasedClassifier()
        self._llm:            LLMClassifier | None = None
        self._umbral          = umbral
        self._llm_desactivado = False   # se activa en primer error de cuota

    def _get_llm(self) -> LLMClassifier:
        if self._llm is None:
            self._llm = LLMClassifier()
        return self._llm

    def _llamar_llm(self, cooc: Coocurrencia) -> RelationResult | None:
        """Llama al LLM; devuelve None si falla. Desactiva LLM en error de cuota."""
        if self._llm_desactivado:
            return None
        try:
            return self._get_llm().classify(cooc)
        except Exception as exc:
            msg = str(exc).lower()
            if "rate_limit" in msg or "429" in msg or "quota" in msg or "limit" in msg:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "LLM desactivado por cuota/rate-limit — resto del run usará solo reglas. "
                    "Error: %s", exc
                )
                self._llm_desactivado = True
            return None

    def classify(self, cooc: Coocurrencia) -> RelationResult:
        resultado = self._rules.classify(cooc)
        if resultado.confianza >= self._umbral:
            return resultado
        llm_result = self._llamar_llm(cooc)
        if llm_result is None:
            return resultado
        return RelationResult(
            tipo=llm_result.tipo,
            confianza=llm_result.confianza,
            evidencia=llm_result.evidencia,
            metodo="hybrid",
        )

    def classify_grupo(self, coocs: list[Coocurrencia]) -> RelationResult:
        """Clasifica un grupo de co-ocurrencias del mismo par de entidades.

        Aplica reglas a todas, toma la de mayor confianza. Solo llama al LLM
        una vez (con la oración más larga) si ninguna supera el umbral.
        Úsalo en precompute para reducir llamadas LLM de O(co-ocurrencias)
        a O(pares únicos).
        """
        resultados = [(c, self._rules.classify(c)) for c in coocs]
        mejor_cooc, mejor_res = max(
            resultados, key=lambda x: (x[1].confianza, len(x[0].oracion))
        )
        if mejor_res.confianza >= self._umbral:
            return mejor_res

        candidato = max(coocs, key=lambda c: len(c.oracion))
        llm_res = self._llamar_llm(candidato)
        if llm_res is None:
            return mejor_res
        return RelationResult(
            tipo=llm_res.tipo,
            confianza=llm_res.confianza,
            evidencia=llm_res.evidencia,
            metodo="hybrid",
        )
