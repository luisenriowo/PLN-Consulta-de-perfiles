"""Producto — Visor de cronologías generadas (Streamlit, READ-ONLY).

Visualiza las líneas de tiempo YA generadas en `data/salidas/*.json`. NO
regenera nada: no llama al LLM ni recalcula clusters/embeddings. Lee el esquema
`TimelineEntry` actual (fecha, resumen, fuentes) y ordena por fecha ascendente.
Consistente con el producto (§9) y con las convenciones de CLAUDE.md.

Correr:  uv run streamlit run src/app/visor_cronologia.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# Permite `from src...` al ejecutar con `uv run streamlit run` (añade la raíz del repo).
_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from src.schemas import TimelineEntry  # noqa: E402  (tras ajustar sys.path)

# Visor legacy de una sola figura (Humala). El visor multi-figura es la web app
# (src/app/web + endpoints en api.py). Apunta al layout por-figura.
SALIDAS = _RAIZ / "data" / "salidas" / "humala"
CORPUS = _RAIZ / "data" / "corpus_humala.parquet"

# Orden de presentación: Sistema primero (es la salida "buena").
COND_ORDEN = ["sistema_rag", "b1_extractive", "b0_lead", "ablacion"]
ETIQUETAS = {
    "sistema_rag": "Sistema (RAG anclado)",
    "b1_extractive": "B1 — extractivo",
    "b0_lead": "B0 — lead",
    "ablacion": "Ablación (sin anclaje)",
}


@st.cache_data
def cargar_salidas() -> dict[str, list[dict]]:
    """Lee data/salidas/<cond>.json validando contra TimelineEntry."""
    out: dict[str, list[dict]] = {}
    for cond in COND_ORDEN:
        ruta = SALIDAS / f"{cond}.json"
        if not ruta.exists():
            continue
        crudo = json.loads(ruta.read_text(encoding="utf-8"))
        entradas = []
        for e in crudo:
            te = TimelineEntry(
                fecha=date.fromisoformat(e["fecha"]),
                resumen=e.get("resumen", ""),
                fuentes=e.get("fuentes", []),
                confianza=e.get("confianza"),
            )
            entradas.append(
                {
                    "fecha": te.fecha,
                    "resumen": te.resumen,
                    "fuentes": te.fuentes,
                    "cluster_id": te.cluster_id,
                }
            )
        out[cond] = entradas
    return out


@st.cache_data
def cargar_fuentes() -> dict[str, dict]:
    """doc_id -> {url, titulo, lead} desde el corpus (para expandir fuentes)."""
    if not CORPUS.exists():
        return {}
    df = pd.read_parquet(CORPUS, columns=["doc_id", "url", "texto"])
    mapa: dict[str, dict] = {}
    for r in df.itertuples():
        lineas = str(r.texto).split("\n")
        mapa[r.doc_id] = {
            "url": r.url,
            "titulo": lineas[0] if lineas else "",
            "lead": lineas[1] if len(lineas) > 1 else "",
        }
    return mapa


FUENTES_MAP: dict[str, dict] = {}


def _render_fuentes(fuentes: list[str]) -> None:
    """Enlaces clicables (atribución obligatoria) + título/lead al expandir."""
    if not fuentes:
        st.caption("Fuentes: —")
        return
    enlaces = []
    for f in fuentes:
        url = FUENTES_MAP.get(f, {}).get("url")
        enlaces.append(f"[{f}]({url})" if url else f"`{f}`")
    st.caption("Fuentes: " + " · ".join(enlaces))
    with st.expander(f"Ver fuentes ({len(fuentes)})"):
        for f in fuentes:
            info = FUENTES_MAP.get(f, {})
            titulo = info.get("titulo") or "(título no disponible en el corpus)"
            url = info.get("url")
            st.markdown(f"**[{titulo}]({url})**" if url else f"**{titulo}**")
            if info.get("lead"):
                st.write(info["lead"])
            st.caption(f)


def _caja(cond: str, resumen: str | None, *, no_respaldado: bool = False) -> None:
    """Caja de resumen coloreada por condición.

    HOOK: cuando exista la salida del eval con flags de alucinación, pasar
    `no_respaldado=True` para las entradas sin respaldo → se pintan en rojo.
    Por ahora siempre False (comparación cruda).
    """
    if resumen is None:
        st.caption("— (descartado: SIN_RESPALDO)")
        return
    if no_respaldado:
        st.error(resumen)
    elif cond == "sistema_rag":
        st.success(resumen)  # anclado = "bueno"
    elif cond == "ablacion":
        st.warning(resumen)  # sin anclaje = riesgo de alucinación
    else:
        st.info(resumen)  # baselines


def vista_principal(salidas, cond, en_rango) -> None:
    ents = sorted(
        (e for e in salidas[cond] if en_rango(e["fecha"])), key=lambda e: e["fecha"]
    )
    st.subheader(f"{ETIQUETAS[cond]} — {len(ents)} eventos")
    for e in ents:
        with st.container(border=True):
            st.markdown(f"**📅 {e['fecha']}**")
            st.write(e["resumen"] or "_(vacío)_")
            _render_fuentes(e["fuentes"])


def vista_comparacion(salidas, conds, en_rango) -> None:
    # Alinea por cluster_id: cada condición emite una entrada por el MISMO
    # EventCluster, así que el cluster_id las cruza exacto (y la celda del
    # evento que el Sistema descartó queda vacía, no inferida por ausencia).
    # `fecha`/`fuentes` solo como respaldo si un JSON no está backfilleado.
    indice: dict = {}
    for cond in conds:
        for e in salidas[cond]:
            clave = e.get("cluster_id") or (e["fecha"], tuple(sorted(e["fuentes"])))
            d = indice.setdefault(
                clave, {"fecha": e["fecha"], "fuentes": set(), "cond": {}}
            )
            d["fuentes"].update(e["fuentes"])  # unión: robusto si divergen
            d["cond"][cond] = e["resumen"]

    eventos = sorted(
        (d for d in indice.values() if en_rango(d["fecha"])), key=lambda d: d["fecha"]
    )
    st.subheader(f"Comparación de condiciones — {len(eventos)} eventos alineados")
    st.caption(
        "Alineado por `cluster_id`. 🟩 Sistema (anclado) · 🟨 Ablación (sin anclaje, "
        "riesgo de alucinación) · 🟦 baselines. Lee la misma fila entre condiciones: "
        "dónde la Ablación inventa frente al Sistema. (Rojo de no-respaldo: pendiente del eval.)"
    )
    for d in eventos:
        st.markdown(f"### 📅 {d['fecha']}")
        cols = st.columns(len(conds))
        for col, cond in zip(cols, conds):
            with col:
                st.markdown(f"**{ETIQUETAS[cond]}**")
                _caja(cond, d["cond"].get(cond))
        _render_fuentes(sorted(d["fuentes"]))
        st.divider()


def main() -> None:
    global FUENTES_MAP
    st.set_page_config(page_title="Visor de cronologías", page_icon="🗓️", layout="wide")
    st.title("🗓️ Visor de cronologías — Ollanta Humala")
    st.caption(
        "Líneas de tiempo generadas desde noticias (Agencia Andina, 2021–2025). "
        "Caso disputado: todo evento va **atribuido a su fuente**, nada se afirma como hecho."
    )

    salidas = cargar_salidas()
    FUENTES_MAP = cargar_fuentes()
    if not salidas:
        st.error(
            "No hay salidas en `data/salidas/`. Corre primero "
            "`uv run python scripts/run_generation.py`."
        )
        st.stop()

    conds = [c for c in COND_ORDEN if c in salidas]
    todas = [e["fecha"] for ents in salidas.values() for e in ents]
    fmin, fmax = min(todas), max(todas)

    st.sidebar.header("Controles")
    comparar = st.sidebar.toggle("Comparar condiciones", value=False)
    cond_sel = st.sidebar.selectbox(
        "Condición (vista principal)",
        conds,
        format_func=lambda c: ETIQUETAS[c],
        index=0,
        disabled=comparar,
    )
    if fmin < fmax:
        rango = st.sidebar.slider(
            "Rango de fechas",
            min_value=fmin,
            max_value=fmax,
            value=(fmin, fmax),
            format="YYYY-MM-DD",
        )
    else:
        rango = (fmin, fmax)
    st.sidebar.caption(
        f"{len(conds)} condiciones cargadas · {len(todas)} entradas totales"
    )

    def en_rango(f: date) -> bool:
        return rango[0] <= f <= rango[1]

    if comparar:
        vista_comparacion(salidas, conds, en_rango)
    else:
        vista_principal(salidas, cond_sel, en_rango)


if __name__ == "__main__":
    main()
