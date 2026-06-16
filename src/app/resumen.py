"""Resumen en números de una figura (read-only, sin LLM).

Dos bloques con estatus epistémico DISTINTO:

  Bloque 1 — Cobertura y sistema: conteos exactos y verificables del dataset
  (hitos, rango, notas, eventos por condición, descartes por SIN_RESPALDO, y un
  slot reservado para la tasa de alucinación medida). Son hechos.

  Bloque 2 — Caso por tipo procesal: CATEGORIZACIÓN del sistema por reglas sobre
  el texto de las fuentes (NO un hecho del artículo). Cada evento se clasifica en
  una taxonomía controlada y se acompaña del SPAN-FUENTE que disparó la etiqueta,
  con enlace a la nota — la cita respalda la etiqueta; el número/categoría son
  inferencia del sistema. Preserva el estatus en disputa (primera instancia /
  apelada / firme); no colapsa a "condena" firme.

Hook para el gold: `computar(..., gold=...)`. Si existe un gold con tipo/estatus
procesal etiquetado por humanos (keyed por cluster_id), el Bloque 2 lee ESOS
tipos verificados en vez de las reglas; `fuente_clasificacion` pasa de "reglas"
a "gold_humano" y la UI no cambia (solo el rótulo y la fuente del dato).
"""

from __future__ import annotations

import re

# Taxonomía procesal controlada, en ORDEN DE PRIORIDAD (el acto más decisivo
# gana). Auditable: el span-fuente mostrado deja ver por qué se clasificó así.
TAXONOMIA: list[tuple[str, re.Pattern]] = [
    ("sentencia", re.compile(
        r"sentenci|conden[oó]|conden[ae]|absol|absuel|fallo condenatorio|"
        r"a[ñn]os de (prisi[oó]n|c[aá]rcel)|pena de", re.I)),
    ("apelacion", re.compile(
        r"apelaci[oó]n|apel[oó]|segunda instancia|casaci[oó]n|"
        r"sala penal de apelaciones|confirm[oó] la (sentencia|condena)|revoc", re.I)),
    ("medida_cautelar", re.compile(
        r"prisi[oó]n preventiva|prisi[oó]n preliminar|detenci[oó]n preliminar|"
        r"impedimento de salida|comparecencia|allanamiento|incautaci[oó]n|"
        r"cauci[oó]n|grillete|arresto domiciliario", re.I)),
    ("imputacion_acusacion", re.compile(
        r"acusaci[oó]n|acus[oó]|imputa|formaliz|requerimiento (mixto|de acusaci[oó]n)|"
        r"denuncia (constitucional|penal|fiscal)", re.I)),
    ("audiencia", re.compile(
        r"audiencia|juicio oral|vista de la causa|diligencia|interrogatorio|alegatos", re.I)),
]
TIPOS = [t for t, _ in TAXONOMIA] + ["otro"]

ETIQUETAS_TIPO = {
    "sentencia": "Sentencia",
    "apelacion": "Apelación / impugnación",
    "medida_cautelar": "Medida cautelar",
    "imputacion_acusacion": "Imputación / acusación",
    "audiencia": "Audiencia / diligencia",
    "otro": "Otro",
}

# Estatus (solo se reporta para sentencia/apelación): preserva lo disputado.
_ESTATUS = [
    (re.compile(r"primera instancia", re.I), "primera instancia"),
    (re.compile(r"segunda instancia|apelaci[oó]n|apelad", re.I), "en apelación"),
    (re.compile(r"confirm|ratific", re.I), "confirmada"),
    (re.compile(r"\bfirme\b|consentida|ejecutoriada", re.I), "firme"),
]

# Delitos nombrados (imputaciones MENCIONADAS, no "investigaciones activas").
DELITOS: dict[str, re.Pattern] = {
    "lavado de activos": re.compile(r"lavado de (activos|dinero)", re.I),
    "organización criminal": re.compile(r"organizaci[oó]n criminal", re.I),
    "asociación ilícita": re.compile(r"asociaci[oó]n il[ií]cita", re.I),
    "colusión": re.compile(r"colusi[oó]n", re.I),
    "cohecho / soborno": re.compile(r"cohecho|soborno", re.I),
    "tráfico de influencias": re.compile(r"tr[aá]fico de influencias", re.I),
    "peculado": re.compile(r"peculado", re.I),
    "enriquecimiento ilícito": re.compile(r"enriquecimiento il[ií]cito", re.I),
    "obstrucción a la justicia": re.compile(r"obstrucci[oó]n", re.I),
    "falsedad": re.compile(r"falsedad (gen[eé]rica|ideol[oó]gica)|falsedad", re.I),
}

_FIN = re.compile(r"(?<=[.!?])\s+")


def _spans(ev: dict):
    """(frase, doc_id, url) candidatas: título y lead de cada fuente del evento."""
    for f in ev.get("fuentes", []):
        for bloque in (f.get("titulo", ""), f.get("lead", "")):
            for frase in _FIN.split(bloque.strip()):
                frase = frase.strip()
                if frase:
                    yield frase, f.get("doc_id", ""), f.get("url", "")


def _estatus(span: str) -> str | None:
    for pat, etq in _ESTATUS:
        if pat.search(span):
            return etq
    return None


def _clasificar(ev: dict) -> dict:
    """Tipo procesal + span-fuente que lo disparó (auditable)."""
    candidatos = list(_spans(ev))
    for tipo, pat in TAXONOMIA:
        for frase, doc_id, url in candidatos:
            if pat.search(frase):
                est = _estatus(frase) if tipo in ("sentencia", "apelacion") else None
                return {"tipo": tipo, "span": frase, "doc_id": doc_id, "url": url, "estatus": est}
    # "Otro": no se detectó acto procesal (típico de eventos políticos, no
    # judiciales). Mostramos el titular representativo como CONTEXTO del evento
    # — no es un trigger procesal, solo dice de qué trata.
    f0 = ev["fuentes"][0] if ev.get("fuentes") else {}
    return {"tipo": "otro", "span": f0.get("titulo") or None,
            "doc_id": f0.get("doc_id"), "url": f0.get("url"), "estatus": None}


def _delitos(eventos: list[dict]) -> list[dict]:
    """Imputaciones nombradas con su span-fuente (dedup por delito)."""
    salida: list[dict] = []
    vistos: set[str] = set()
    for ev in eventos:
        for frase, doc_id, url in _spans(ev):
            for nombre, pat in DELITOS.items():
                if nombre not in vistos and pat.search(frase):
                    vistos.add(nombre)
                    salida.append({"delito": nombre, "span": frase, "doc_id": doc_id, "url": url})
    return salida


def computar(figura: dict, *, n_notas_corpus: int, gold: dict | None = None) -> dict:
    """Construye el resumen (bloques 1 y 2) desde el payload de la figura."""
    eventos = figura["eventos"]
    conds = figura["condiciones"]
    fechas = [e["fecha"] for e in eventos]

    bloque1 = {
        "n_hitos": len(eventos),
        "rango_fechas": [min(fechas), max(fechas)] if fechas else [None, None],
        "n_notas_corpus": n_notas_corpus,
        "n_notas_citadas": len({f["doc_id"] for e in eventos for f in e["fuentes"]}),
        "eventos_por_condicion": {c: sum(1 for e in eventos if c in e["por_condicion"]) for c in conds},
        "descartados_sistema": len(eventos) - sum(1 for e in eventos if "sistema_rag" in e["por_condicion"]),
        "tasa_alucinacion": None,   # slot reservado: lo llena la salida del eval
    }

    # Bloque 2: gold verificado si existe; si no, reglas.
    por_tipo: dict[str, dict] = {t: {"n": 0, "etiqueta": ETIQUETAS_TIPO[t], "eventos": []} for t in TIPOS}
    for ev in eventos:
        cid = ev["cluster_id"]
        c = (gold.get(cid) if gold else None) or _clasificar(ev)
        t = c.get("tipo", "otro")
        por_tipo.setdefault(t, {"n": 0, "etiqueta": ETIQUETAS_TIPO.get(t, t), "eventos": []})
        por_tipo[t]["n"] += 1
        por_tipo[t]["eventos"].append({
            "cluster_id": cid, "fecha": ev["fecha"],
            "span": c.get("span"), "doc_id": c.get("doc_id"),
            "url": c.get("url"), "estatus": c.get("estatus"),
        })

    bloque2 = {
        "fuente_clasificacion": "gold_humano" if gold else "reglas",
        "por_tipo": por_tipo,
        "delitos": _delitos(eventos),
    }
    return {"slug": figura["slug"], "nombre": figura["nombre"], "bloque1": bloque1, "bloque2": bloque2}
