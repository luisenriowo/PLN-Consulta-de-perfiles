"use strict";

// Metadatos de presentación de cada condición (orden = como llega de la API).
const COND = {
  sistema_rag:   { etq: "Sistema · RAG anclado",    clase: "c-sistema",  tag: "anclado" },
  b1_extractive: { etq: "B1 · extractivo",          clase: "c-base",     tag: null },
  b0_lead:       { etq: "B0 · lead",                clase: "c-base",     tag: null },
  ablacion:      { etq: "Ablación · sin anclaje",   clase: "c-ablacion", tag: "sin anclaje" },
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const fmtDia = new Intl.DateTimeFormat("es", { weekday: "long" });
const fmtFecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "long", year: "numeric" });

let FIGURA = null;   // payload de la figura actual

function fechaHTML(iso) {
  const d = new Date(iso + "T00:00:00");
  return `<span class="fecha"><span class="dia">${esc(fmtDia.format(d))}</span>${esc(fmtFecha.format(d))}</span>`;
}

function fuentesHTML(fuentes) {
  if (!fuentes || !fuentes.length) return `<p class="fuentes"><span class="docid">sin fuentes</span></p>`;
  const items = fuentes.map((f) => {
    const titulo = f.titulo || "(título no disponible en el corpus)";
    const cabeza = f.url
      ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(titulo)}</a>`
      : `<strong>${esc(titulo)}</strong>`;
    const lead = f.lead ? `<p class="lead">${esc(f.lead)}</p>` : "";
    return `<li>${cabeza}${lead}<div class="docid">${esc(f.doc_id)}</div></li>`;
  }).join("");
  return `<details class="fuentes"><summary>${fuentes.length} fuente${fuentes.length > 1 ? "s" : ""}</summary><ol>${items}</ol></details>`;
}

function eventoPrincipalHTML(ev) {
  const txt = ev.por_condicion.sistema_rag;
  const cuerpo = txt
    ? `<p class="descripcion">${esc(txt)}</p>`
    : `<p class="descripcion descartado">— el Sistema descartó este evento (sin respaldo).</p>`;
  return `<article class="evento">${fechaHTML(ev.fecha)}${cuerpo}${fuentesHTML(ev.fuentes)}</article>`;
}

function condHTML(cond, texto) {
  const m = COND[cond] || { etq: cond, clase: "c-base", tag: null };
  const tag = m.tag ? `<span class="tag">${esc(m.tag)}</span>` : "";
  const cuerpo = texto == null
    ? `<div class="texto descartado">— descartado: SIN_RESPALDO</div>`
    : `<div class="texto">${esc(texto)}</div>`;
  return `<div class="cond ${m.clase}"><div class="etq">${esc(m.etq)}${tag}</div>${cuerpo}</div>`;
}

function eventoComparacionHTML(ev) {
  const conds = FIGURA.condiciones.map((c) => condHTML(c, ev.por_condicion[c] ?? null)).join("");
  return `<article class="evento">${fechaHTML(ev.fecha)}<div class="condiciones">${conds}</div>${fuentesHTML(ev.fuentes)}</article>`;
}

function render() {
  if (!FIGURA) return;
  const desde = $("desde").value, hasta = $("hasta").value;
  const comparar = $("comparar").checked;

  let eventos = FIGURA.eventos.filter((e) =>
    (!desde || e.fecha >= desde) && (!hasta || e.fecha <= hasta));
  // Vista principal = línea de tiempo del Sistema: solo eventos que el Sistema produjo.
  if (!comparar) eventos = eventos.filter((e) => e.por_condicion.sistema_rag != null);

  const n = eventos.length;
  $("meta").innerHTML = comparar
    ? `<strong>${esc(FIGURA.nombre)}</strong> — comparación de ${FIGURA.condiciones.length} condiciones · ${n} eventos`
    : `<strong>${esc(FIGURA.nombre)}</strong> — Sistema (RAG anclado) · ${n} eventos`;
  $("aviso").hidden = false;

  const html = eventos.map(comparar ? eventoComparacionHTML : eventoPrincipalHTML).join("");
  $("timeline").innerHTML = html;
  $("vacio").hidden = n > 0;
}

async function cargarFigura(slug) {
  try {
    const r = await fetch(`api/figuras/${slug}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    FIGURA = await r.json();
    const fechas = FIGURA.eventos.map((e) => e.fecha);
    if (fechas.length) {
      const min = fechas.reduce((a, b) => a < b ? a : b);
      const max = fechas.reduce((a, b) => a > b ? a : b);
      $("desde").min = $("hasta").min = min;
      $("desde").max = $("hasta").max = max;
      $("desde").value = min; $("hasta").value = max;
    }
    render();
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent = `No se pudo cargar la figura: ${e.message}`;
  }
}

async function init() {
  try {
    const r = await fetch("api/figuras");
    const figuras = await r.json();
    if (!figuras.length) {
      $("error").hidden = false;
      $("error").textContent = "No hay figuras procesadas. Precomputa una con scripts/precompute_figura.py.";
      return;
    }
    const sel = $("figura");
    sel.innerHTML = figuras.map((f) =>
      `<option value="${esc(f.slug)}">${esc(f.nombre)} (${f.n_eventos})</option>`).join("");
    sel.onchange = () => cargarFigura(sel.value);
    ["desde", "hasta", "comparar"].forEach((id) => $(id).addEventListener("input", render));
    cargarFigura(figuras[0].slug);
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent = `No se pudo conectar con el backend: ${e.message}`;
  }
}

init();
