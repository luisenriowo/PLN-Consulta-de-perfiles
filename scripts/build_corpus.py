"""Construye el corpus 2021–2025 de Humala (v2) y reporta gate-metrics.

Densifica ANTES de persistir, para construir una sola vez:
  - Andina (PRIMARIA), queries de TÉRMINO suelto (la búsqueda es por frase, así
    que multi-palabra falla): "Ollanta Humala", "Odebrecht", "Gasoducto Sur",
    "Madre Mía", "Lava Jato". Más "Nadine Heredia" SOLO como descubrimiento.
    El filtro de protagonismo descarta lo que no es sobre Humala.
  - GDELT (SECUNDARIA): aporta medios INDEPENDIENTES (sobre todo ~2025) → es lo
    que habilita la señal de saliencia multi-fuente (bonus). Solo titular.

⚠ El corpus se concentra en la saga judicial Odebrecht → DECLÁRALO en la nota
metodológica del informe.

Gate-metrics (deciden go/no-go, CLAUDE.md §8):
  (1) Conteo EFECTIVO: docs con Humala como SUJETO (no solo mencionado).
  (2) Dedup: dup exacta (preprocess) vs redundancia near-dup (clustering).
  (3) Diversidad de fuentes: nº de medios independientes (vía GDELT).

Persiste en data/corpus_humala.parquet (data/ gitignored).
Uso:  python scripts/build_corpus.py
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from src.ingest import andina, gdelt
from src.ingest._util import (
    FECHA_CORTE_HUMALA,
    FECHA_INICIO_HUMALA,
    dentro_de_ventana,
    http_session,
)
from src.pipeline import entities, preprocess

SUJETO = "Ollanta Humala"
SUJETO_ID = "humala:ollanta"
MODELO = "es_core_news_md"   # smoke/desarrollo; producción usa lg
DELAY = 0.4                  # cortesía entre descargas de notas

# Queries de término suelto (Andina busca por frase). Valor = rol.
QUERIES_ANDINA = {
    "Ollanta Humala": "principal",
    "Odebrecht": "termino",
    "Gasoducto Sur": "termino",
    "Madre Mía": "termino",
    "Lava Jato": "termino",
    "Nadine Heredia": "descubrimiento",
}
SALIDA_PARQUET = Path("data/corpus_humala.parquet")
SALIDA_METRICS = Path("data/corpus_metrics.json")


def descubrir_andina(session) -> dict[str, set[str]]:
    """URL -> conjunto de queries que la encontraron (dedup por URL)."""
    procedencia: dict[str, set[str]] = {}
    for q in QUERIES_ANDINA:
        urls = andina.buscar(session, q)
        print(f"  query {q!r}: {len(urls)} URLs")
        for u in urls:
            procedencia.setdefault(u, set()).add(q)
    return procedencia


def _shingles(texto: str, k: int = 2) -> set[tuple[str, ...]]:
    toks = re.findall(r"\w+", texto.lower())
    return {tuple(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def stats_near_dup(docs) -> dict:
    """Dup exacta ya la hizo preprocess; aquí, redundancia near-dup (bigramas)."""
    sh = [_shingles(d.texto) for d in docs]
    identicos = redundantes = 0
    docs_redundantes: set[int] = set()
    n = len(docs)
    for i in range(n):
        for j in range(i + 1, n):
            if not sh[i] or not sh[j]:
                continue
            r = len(sh[i]) / len(sh[j]) if len(sh[j]) else 0
            if r and (r < 0.4 or r > 2.5):
                continue
            jac = _jaccard(sh[i], sh[j])
            if jac >= 0.9:
                identicos += 1
                docs_redundantes |= {i, j}
            elif jac >= 0.4:
                redundantes += 1
                docs_redundantes |= {i, j}
    return {
        "pares_casi_identicos_j>=0.9": identicos,
        "pares_mismo_evento_0.4<=j<0.9": redundantes,
        "docs_involucrados_en_redundancia": len(docs_redundantes),
        "total_docs": n,
    }


def _prefijo_titular(texto: str) -> int:
    """Largo del bloque título+lead (primeras 2 líneas del texto de Andina)."""
    lineas = texto.split("\n")
    if len(lineas) >= 2:
        return len(lineas[0]) + 1 + len(lineas[1])
    return len(lineas[0])


def clasificar_protagonismo(doc) -> str:
    """'protagonista' | 'solo_mencionado' | 'no_mencionado'.

    protagonista := Humala aparece en título/lead, O es la persona dominante
    (≥2 menciones y nadie lo supera). Mención sin protagonismo = lateral.
    """
    menciones = [e for e in doc.entidades if e.entidad_id == SUJETO_ID]
    if not menciones:
        return "no_mencionado"
    prefijo = _prefijo_titular(doc.texto)
    en_titular = any(e.inicio <= prefijo for e in menciones)

    per = Counter()
    for e in doc.entidades:
        if e.tipo == "PER":
            per[e.entidad_id or e.texto.lower()] += 1
    n_ollanta = per.get(SUJETO_ID, 0)
    dominante = n_ollanta >= 2 and n_ollanta >= max(per.values())

    return "protagonista" if (en_titular or dominante) else "solo_mencionado"


def _tipo_fuente(doc) -> str:
    return "andina" if doc.fuente == "andina.pe" else "gdelt"


def main() -> None:
    session = http_session()

    print("== DESCUBRIMIENTO ANDINA (multi-query término) ==")
    procedencia = descubrir_andina(session)
    total_pares = sum(len(qs) for qs in procedencia.values())
    print(f"  URLs únicas: {len(procedencia)}  | solapamiento: "
          f"{total_pares - len(procedencia)}")

    print("== DESCARGA + PARSEO Andina ==")
    docs = []
    proc_map: dict[str, str] = {}
    fuera_ventana = fallidas = 0
    for k, (url, queries) in enumerate(procedencia.items(), 1):
        doc = andina.parse_nota(session, url)
        if doc is None:
            fallidas += 1
        elif not dentro_de_ventana(doc.fecha_pub, hasta=FECHA_CORTE_HUMALA):
            fuera_ventana += 1
        else:
            proc_map[doc.doc_id] = ",".join(sorted(queries))
            docs.append(doc)
        if k % 100 == 0:
            print(f"  {k}/{len(procedencia)}  (ok={len(docs)} fuera={fuera_ventana})")
        time.sleep(DELAY)
    print(f"  Andina en ventana: {len(docs)} (fuera={fuera_ventana}, fail={fallidas})")

    print("== GDELT (secundaria: medios independientes) ==")
    try:
        gdelt_docs = gdelt.collect(SUJETO, FECHA_CORTE_HUMALA, maxrecords=250)
        gdelt_docs = [d for d in gdelt_docs if dentro_de_ventana(d.fecha_pub, hasta=FECHA_CORTE_HUMALA)]
        for d in gdelt_docs:
            proc_map[d.doc_id] = "gdelt"
        rango = sorted(d.fecha_pub for d in gdelt_docs)
        print(f"  GDELT en ventana: {len(gdelt_docs)}"
              + (f"  rango {rango[0]}…{rango[-1]}" if rango else "")
              + f"  medios: {len({d.fuente for d in gdelt_docs})}")
        docs += gdelt_docs
    except Exception as exc:   # noqa: BLE001
        print(f"  GDELT no disponible: {exc!r}")

    print("== PREPROCESS (limpieza + dedup exacta) ==")
    antes = len(docs)
    limpios = preprocess.preprocess(docs)
    dup_exacta = antes - len(limpios)
    print(f"  dedup exacta: {dup_exacta} eliminadas  | quedan {len(limpios)}")

    print("== NEAR-DUP (redundancia de evento; NO se elimina) ==")
    dedup = stats_near_dup(limpios)
    for kk, vv in dedup.items():
        print(f"  {kk}: {vv}")
    dedup["dup_exacta_eliminadas"] = dup_exacta

    print(f"== ENTITIES (NER={MODELO} + linking) ==")
    anotados = entities.link_entities(limpios, modelo=MODELO)

    print("== PROTAGONISMO (gate-metric 1) ==")
    clase = {d.doc_id: clasificar_protagonismo(d) for d in anotados}
    clases = Counter(clase.values())
    protag = [d for d in anotados if clase[d.doc_id] == "protagonista"]
    print(f"  protagonista: {len(protag)}  | solo_mencionado: {clases['solo_mencionado']}"
          f"  | no_mencionado: {clases['no_mencionado']}")
    print(f"  CORPUS EFECTIVO: {len(protag)} de {len(anotados)}")

    # por fuente y por año (corpus efectivo)
    por_fuente = Counter(_tipo_fuente(d) for d in protag)
    anios = Counter(d.fecha_pub.year for d in protag)
    print(f"  efectivo por fuente: {dict(por_fuente)}")
    print(f"  efectivo por año: {dict(sorted(anios.items()))}")

    print("== DIVERSIDAD DE FUENTES (gate-metric 3) ==")
    medios_protag = {d.fuente for d in protag}
    medios_gdelt = {d.fuente for d in protag if _tipo_fuente(d) == "gdelt"}
    print(f"  medios distintos en corpus efectivo: {len(medios_protag)}"
          f"  (independientes vía GDELT: {len(medios_gdelt)})")
    print(f"  ejemplos GDELT: {sorted(medios_gdelt)[:8]}")

    # --- persistir ---
    filas = [{
        "doc_id": d.doc_id,
        "fuente": d.fuente,
        "source": _tipo_fuente(d),
        "url": d.url,
        "fecha_pub": d.fecha_pub.isoformat(),
        "texto": d.texto,
        "queries": proc_map.get(d.doc_id, ""),
        "n_ent_ollanta": sum(1 for e in d.entidades if e.entidad_id == SUJETO_ID),
        "clase_protagonismo": clase[d.doc_id],
        "humala_protagonista": clase[d.doc_id] == "protagonista",
        "entidades": json.dumps([e.model_dump() for e in d.entidades], ensure_ascii=False),
    } for d in anotados]
    SALIDA_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).to_parquet(SALIDA_PARQUET, index=False)
    print(f"\n== PERSISTIDO ==\n  {SALIDA_PARQUET} ({len(filas)} filas)")

    metrics = {
        "ventana": [FECHA_INICIO_HUMALA.isoformat(), FECHA_CORTE_HUMALA.isoformat()],
        "queries_andina": QUERIES_ANDINA,
        "andina_en_ventana": len(docs) - sum(1 for d in anotados if _tipo_fuente(d) == "gdelt"),
        "dedup": dedup,
        "protagonismo": dict(clases),
        "corpus_efectivo": len(protag),
        "efectivo_por_fuente": dict(por_fuente),
        "efectivo_por_anio": dict(sorted(anios.items())),
        "medios_distintos_efectivo": len(medios_protag),
        "medios_independientes_gdelt": len(medios_gdelt),
    }
    SALIDA_METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {SALIDA_METRICS}")


if __name__ == "__main__":
    main()
