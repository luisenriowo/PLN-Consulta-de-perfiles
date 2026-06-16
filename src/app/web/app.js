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

// ---------- Resumen en números (panel secundario, read-only) ----------
const fmtMesAnio = new Intl.DateTimeFormat("es", { month: "short", year: "numeric" });
const fechaCorta = (iso) => iso ? fmtMesAnio.format(new Date(iso + "T00:00:00")) : "—";

function statHTML(valor, etiqueta, nota) {
  return `<div class="stat"><div class="num">${esc(valor)}</div>` +
    `<div class="lbl">${esc(etiqueta)}</div>${nota ? `<div class="nota">${esc(nota)}</div>` : ""}</div>`;
}

function eventoTipoHTML(e) {
  const est = e.estatus ? `<span class="estatus">${esc(e.estatus)}</span>` : "";
  const span = e.span
    ? (e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">“${esc(e.span)}”</a>` : `“${esc(e.span)}”`)
    : `<span class="muted">— sin span procesal</span>`;
  return `<li><span class="ev-fecha">${esc(e.fecha)}</span>${est}<span class="ev-span">${span}</span></li>`;
}

function tipoHTML(v) {
  const evs = v.eventos.map(eventoTipoHTML).join("");
  return `<details class="tipo"><summary><span class="t-etq">${esc(v.etiqueta)}</span>` +
    `<span class="t-n">${v.n}</span></summary><ul>${evs}</ul></details>`;
}

function delitoHTML(d) {
  const span = d.url
    ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">“${esc(d.span)}”</a>`
    : `“${esc(d.span)}”`;
  return `<li><strong>${esc(d.delito)}</strong> ${span}</li>`;
}

function renderResumen(R) {
  const b1 = R.bloque1, b2 = R.bloque2;
  const cards = [
    statHTML(b1.n_hitos, "hitos"),
    statHTML(`${fechaCorta(b1.rango_fechas[0])} – ${fechaCorta(b1.rango_fechas[1])}`, "rango"),
    statHTML(b1.n_notas_corpus, "notas en el corpus"),
    statHTML(b1.n_notas_citadas, "notas citadas"),
    statHTML(b1.descartados_sistema, "descartados (SIN_RESPALDO)"),
    statHTML(
      b1.tasa_alucinacion == null ? "—" : (b1.tasa_alucinacion * 100).toFixed(1) + "%",
      "tasa de alucinación",
      b1.tasa_alucinacion == null ? "pendiente del eval" : "Sistema vs Ablación"),
  ].join("");
  const porCond = Object.entries(b1.eventos_por_condicion)
    .map(([c, n]) => `${(COND[c] && COND[c].etq) || c}: ${n}`).join(" · ");

  const disclaimer = b2.fuente_clasificacion === "gold_humano"
    ? "Tipos verificados por anotación humana (gold)."
    : "Categorización automática del sistema sobre el corpus — auditable, no es un registro legal oficial.";
  const tipos = Object.entries(b2.por_tipo).filter(([, v]) => v.n > 0)
    .map(([, v]) => tipoHTML(v)).join("");
  const delitos = b2.delitos.length
    ? b2.delitos.map(delitoHTML).join("")
    : `<li class="muted">ninguna imputación nombrada detectada</li>`;

  $("resumen").innerHTML = `
    <details class="resumen">
      <summary>Resumen en números</summary>
      <div class="bloque b1">
        <h3>Cobertura y sistema <span class="status-tag fact">hechos del corpus</span></h3>
        <div class="b1-grid">${cards}</div>
        <p class="por-cond">Eventos por condición — ${esc(porCond)}</p>
      </div>
      <div class="bloque b2">
        <h3>Caso, por tipo procesal <span class="status-tag infer">inferencia del sistema</span></h3>
        <p class="disclaimer">${esc(disclaimer)} Cada tipo es clicable: muestra el <em>span-fuente</em> que disparó la etiqueta.</p>
        <div class="tipos">${tipos}</div>
        <h4>Delitos / imputaciones mencionadas</h4>
        <ul class="delitos">${delitos}</ul>
      </div>
    </details>`;
}

async function cargarResumen(slug) {
  try {
    const r = await fetch(`api/figuras/${slug}/resumen`);
    if (r.ok) renderResumen(await r.json());
  } catch { /* panel secundario: si falla, no bloquea el visor */ }
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
    cargarResumen(slug);
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent = `No se pudo cargar la figura: ${e.message}`;
  }
}

// ---------- Crear figura nueva (job en background) ----------
async function recargarFiguras(seleccionar) {
  const figuras = await (await fetch("api/figuras")).json();
  const sel = $("figura");
  sel.innerHTML = figuras.map((f) =>
    `<option value="${esc(f.slug)}">${esc(f.nombre)} (${f.n_eventos})</option>`).join("");
  if (seleccionar) sel.value = seleccionar;
  cargarFigura(sel.value);
}

function pollJob(slug, el) {
  const t = setInterval(async () => {
    try {
      const s = await (await fetch(`api/jobs/${slug}`)).json();
      const log = (s.log || []).slice(-3).map(esc).join("<br>");
      if (s.estado === "running") {
        el.innerHTML = `<span class="spin">◴</span> Procesando <strong>${esc(slug)}</strong>… ` +
          `<div class="joblog">${log}</div>`;
      } else if (s.estado === "done") {
        clearInterval(t);
        el.innerHTML = `✓ <strong>${esc(slug)}</strong> lista — cargando…`;
        await recargarFiguras(slug);
        $("nueva").hidden = true;
      } else if (s.estado === "error") {
        clearInterval(t);
        el.innerHTML = `✗ Error procesando <strong>${esc(slug)}</strong>: ${esc(s.error || "")}`;
      }
    } catch { /* reintenta en el próximo tick */ }
  }, 3000);
}

function initNueva() {
  $("btn-nueva").addEventListener("click", () => { $("nueva").hidden = !$("nueva").hidden; });
  $("form-nueva").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const nombre = $("n-nombre").value.trim();
    if (!nombre) return;
    const split = (id) => $(id).value.split(",").map((s) => s.trim()).filter(Boolean);
    const el = $("n-estado");
    el.textContent = "Lanzando…";
    try {
      const r = await fetch("api/figuras", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre, homonimos: split("n-homonimos"), terminos: split("n-terminos") }),
      });
      const s = await r.json();
      if (s.estado === "done") {
        el.innerHTML = `Ya existía — cargando…`;
        await recargarFiguras(s.slug); $("nueva").hidden = true; return;
      }
      pollJob(s.slug, el);
    } catch (e) { el.textContent = "Error al lanzar: " + e.message; }
  });
}

async function init() {
  initNueva();
  try {
    const r = await fetch("api/figuras");
    const figuras = await r.json();
    if (!figuras.length) {
      $("error").hidden = false;
      $("error").textContent = "No hay figuras procesadas. Usa “+ Nueva figura” para crear una.";
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
