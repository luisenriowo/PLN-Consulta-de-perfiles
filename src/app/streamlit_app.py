"""Producto — Frontend Streamlit (OBLIGATORIO, CLAUDE.md §9).

Interfaz usable: el usuario elige la condición de generación y ve la línea de
tiempo del sujeto con sus fuentes citadas. Consume el backend FastAPI. Usable,
nada más (no sobre-ingenierizar, §10).

Levantar (con el backend ya corriendo):
    uv run streamlit run src/app/streamlit_app.py
"""

from __future__ import annotations

import os

import requests
import streamlit as st

API = os.environ.get("TIMELINE_API", "http://127.0.0.1:8000")

st.set_page_config(page_title="timeline-gen", page_icon="🗓️", layout="centered")
st.title("🗓️ Línea de tiempo — figuras políticas")
st.caption(
    "Generada desde un corpus de noticias (Agencia Andina, 2021–2025). "
    "Caso disputado: todo evento va **atribuido a su fuente**, nada se afirma como hecho."
)

try:
    info = requests.get(f"{API}/", timeout=5).json()
    condiciones = info.get("condiciones", [])
except requests.RequestException:
    st.error(f"No se pudo conectar al backend en {API}. Levántalo con "
             "`uv run uvicorn src.app.api:app`.")
    st.stop()

if not condiciones:
    st.warning("No hay condiciones generadas. Corre `uv run python scripts/run_generation.py`.")
    st.stop()

st.markdown(f"**Sujeto:** {info.get('sujeto', '—')}")
cond = st.selectbox("Condición de generación", condiciones)

data = requests.get(f"{API}/timeline/{cond}", timeout=10).json()
entradas = data.get("entradas", [])
st.markdown(f"### {len(entradas)} eventos · `{cond}`")

for e in entradas:
    st.markdown(f"**{e['fecha']}** — {e['resumen']}")
    fuentes = e.get("fuentes", [])
    enlaces = [
        f"[{f['doc_id']}]({f['url']})" if f.get("url") else f["doc_id"]
        for f in fuentes
    ]
    st.caption("Fuentes: " + (", ".join(enlaces) if enlaces else "—"))
    st.divider()
