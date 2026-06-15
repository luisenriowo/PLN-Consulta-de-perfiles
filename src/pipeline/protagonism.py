"""Backbone — Filtro de protagonismo (FIJO, compartido por las 4 condiciones).

Clasifica cada `Documento` por el ROL del sujeto (Ollanta Humala) según el
entity linking: ¿es el evento SOBRE él, o solo lo menciona? Es un filtro
documento-nivel previo al clustering; su salida alimenta por igual a las 4
condiciones, así que no debe sesgar la comparación.

Regla (precisión > recall, para no colar eventos de otros miembros de la
familia a la línea de tiempo de Ollanta):

  protagonista  := Ollanta es sujeto del TÍTULO/lead,
                   O es la persona dominante (≥2 menciones, nadie lo supera) Y
                   ningún OTRO familiar (Antauro/Isaac/Nadine) titula la nota.
  solo_mencionado := aparece pero lateral.
  no_mencionado   := no aparece (matcheó por otro término).

El guard del "otro familiar en el título" es lo que excluye casos como
"Antauro Humala sale en libertad" o "Nadine Heredia viaja por salud", donde
Ollanta se menciona en el cuerpo pero el evento NO es suyo.
"""

from __future__ import annotations

from collections import Counter

from src.schemas import Documento

SUJETO_DEFECTO = "humala:ollanta"
# Otros miembros de la familia cuyo protagonismo en el título descarta la nota.
_FAMILIA_OTROS = {"humala:antauro", "humala:isaac", "heredia:nadine"}


def _prefijo_titular(texto: str) -> int:
    """Largo del bloque título+lead (primeras 2 líneas del texto de Andina)."""
    lineas = texto.split("\n")
    if len(lineas) >= 2:
        return len(lineas[0]) + 1 + len(lineas[1])
    return len(lineas[0])


def clasificar(
    doc: Documento,
    sujeto_id: str = SUJETO_DEFECTO,
    *,
    familia_otros: frozenset[str] | set[str] = _FAMILIA_OTROS,
) -> str:
    """'protagonista' | 'solo_mencionado' | 'no_mencionado'.

    Distingue TÍTULO (línea 0) de lead (línea 1): que Ollanta esté solo en el
    lead como contexto ("esposa de Ollanta Humala") no lo hace protagonista si
    el título es de otro familiar.
    """
    menciones = [e for e in doc.entidades if e.entidad_id == sujeto_id]
    if not menciones:
        return "no_mencionado"

    len_titulo = len(doc.texto.split("\n", 1)[0])
    prefijo = _prefijo_titular(doc.texto)            # título + lead
    en_titulo = any(e.inicio <= len_titulo for e in menciones)
    en_lead = any(e.inicio <= prefijo for e in menciones)
    otro_familiar_en_titulo = any(
        e.entidad_id in familia_otros and e.inicio <= len_titulo
        for e in doc.entidades
    )

    per = Counter(
        e.entidad_id or e.texto.lower() for e in doc.entidades if e.tipo == "PER"
    )
    n_sujeto = per.get(sujeto_id, 0)
    dominante = n_sujeto >= 2 and n_sujeto >= max(per.values())

    if en_titulo:                       # Ollanta encabeza la nota
        return "protagonista"
    if otro_familiar_en_titulo:         # el título es de otro familiar → lateral
        return "solo_mencionado"
    if en_lead or dominante:            # Ollanta es el sujeto aunque no titule
        return "protagonista"
    return "solo_mencionado"
