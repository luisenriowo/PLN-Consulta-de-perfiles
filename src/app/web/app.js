"use strict";

const COND = {
  sistema_rag:   { etq: "Sistema · RAG anclado",  clase: "c-sistema",  tag: "anclado" },
  b1_extractive: { etq: "B1 · extractivo",         clase: "c-base",     tag: null },
  b0_lead:       { etq: "B0 · lead",               clase: "c-base",     tag: null },
  ablacion:      { etq: "Ablación · sin anclaje",  clase: "c-ablacion", tag: "sin anclaje" },
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Único mecanismo de visibilidad: clase CSS "oculto"
const mostrar = (id) => $(id).classList.remove("oculto");
const ocultar = (id) => $(id).classList.add("oculto");

const fmtDia   = new Intl.DateTimeFormat("es", { weekday: "long" });
const fmtFecha = new Intl.DateTimeFormat("es", { day: "numeric", month: "long", year: "numeric" });

let FIGURA             = null;
let CONDICION_ACTIVA   = "sistema_rag";
let _obs               = null;
let _eventosActuales   = [];
let FIGURAS_META       = [];

// ── Helpers HTML ──────────────────────────────────────────────────────────────

function fechaHTML(iso) {
  const d = new Date(iso + "T00:00:00");
  return `<span class="fecha">
    <span class="dia">${esc(fmtDia.format(d))}</span>
    ${esc(fmtFecha.format(d))}
  </span>`;
}

function fuentesHTML(fuentes, idx) {
  if (!fuentes?.length) return "";
  const n = fuentes.length;
  return `<button class="btn-fuentes" data-idx="${idx}">${n} fuente${n > 1 ? "s" : ""}</button>`;
}

function textoHTML(txt) {
  const partes = txt.split(/\s*\*\s+/).filter(s => s.trim());
  return `<ul class="ev-lista">${partes.map(p => `<li>${esc(p.trim())}</li>`).join("")}</ul>`;
}

function eventoPrincipalHTML(ev, idx) {
  const txt    = ev.por_condicion[CONDICION_ACTIVA];
  const cuerpo = txt
    ? textoHTML(txt)
    : `<p class="descripcion descartado">— descartado: sin respaldo en los pasajes.</p>`;
  const lado = idx % 2 === 0 ? "izq" : "der";
  return `<div class="evento-wrap ${lado}">
    <article class="evento">
      ${fechaHTML(ev.fecha)}${cuerpo}${fuentesHTML(ev.fuentes, idx)}
    </article>
  </div>`;
}

function condHTML(cond, texto) {
  const m    = COND[cond] || { etq: cond, clase: "c-base", tag: null };
  const tag  = m.tag ? `<span class="tag">${esc(m.tag)}</span>` : "";
  const body = texto == null
    ? `<div class="texto descartado">— descartado: SIN_RESPALDO</div>`
    : `<div class="texto">${esc(texto)}</div>`;
  return `<div class="cond ${m.clase}">
    <div class="etq">${esc(m.etq)}${tag}</div>${body}
  </div>`;
}

function eventoComparacionHTML(ev, idx) {
  const conds = FIGURA.condiciones.map((c) => condHTML(c, ev.por_condicion[c] ?? null)).join("");
  return `<div class="evento-wrap completo">
    <article class="evento">
      ${fechaHTML(ev.fecha)}<div class="condiciones">${conds}</div>${fuentesHTML(ev.fuentes, idx)}
    </article>
  </div>`;
}

// ── IntersectionObserver para fade-in al scroll ───────────────────────────────

function observarEventos() {
  if (_obs) _obs.disconnect();
  _obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add("visible");
      } else {
        e.target.classList.remove("visible");
      }
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
  // Delay para que el browser pinte el estado inicial (opacity:0) antes de observar
  setTimeout(() => {
    document.querySelectorAll(".evento").forEach(el => _obs.observe(el));
  }, 60);
}

// ── Render ────────────────────────────────────────────────────────────────────

function render() {
  if (window.__vistaGrafo) return;   // la vista grafo se gestiona en grafo.js
  if (!FIGURA) return;

  const desde    = $("desde").value;
  const hasta    = $("hasta").value;
  const comparar = $("comparar").checked;

  // Selector de condición solo en vista simple
  comparar ? ocultar("ctl-condicion") : mostrar("ctl-condicion");
  // Aviso contextual solo en comparación
  comparar ? mostrar("aviso") : ocultar("aviso");

  let eventos = FIGURA.eventos.filter((e) =>
    (!desde || e.fecha >= desde) && (!hasta || e.fecha <= hasta));

  if (!comparar) {
    eventos = eventos.filter((e) => e.por_condicion[CONDICION_ACTIVA] != null);
  }

  const n        = eventos.length;
  const condMeta = COND[CONDICION_ACTIVA] || { etq: CONDICION_ACTIVA };

  $("meta").innerHTML = comparar
    ? `<strong>${esc(FIGURA.nombre)}</strong> — comparación de ${FIGURA.condiciones.length} condiciones · ${n} evento${n !== 1 ? "s" : ""}`
    : `<strong>${esc(FIGURA.nombre)}</strong> — ${esc(condMeta.etq)} · ${n} evento${n !== 1 ? "s" : ""}`;

  _eventosActuales = eventos;
  $("timeline").innerHTML = eventos
    .map((ev, i) => comparar ? eventoComparacionHTML(ev, i) : eventoPrincipalHTML(ev, i))
    .join("");

  observarEventos();
  n > 0 ? ocultar("vacio") : mostrar("vacio");
}

// ── Resumen ───────────────────────────────────────────────────────────────────

const fmtMesAnio = new Intl.DateTimeFormat("es", { month: "short", year: "numeric" });
const fechaCorta = (iso) => iso ? fmtMesAnio.format(new Date(iso + "T00:00:00")) : "—";

function statHTML(valor, etiqueta, nota) {
  return `<div class="stat">
    <div class="num">${esc(valor)}</div>
    <div class="lbl">${esc(etiqueta)}</div>
    ${nota ? `<div class="nota">${esc(nota)}</div>` : ""}
  </div>`;
}

function figuraLabel(f) {
  if (f.tipo === "tema") {
    const n = f.n_relaciones ?? 0;
    return `${f.nombre} · ${n} relaciones`;
  }
  return `${f.nombre} · ${f.n_eventos ?? 0} eventos`;
}

function eventoTipoHTML(e) {
  const est  = e.estatus ? `<span class="estatus">${esc(e.estatus)}</span>` : "";
  const span = e.span
    ? (e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">"${esc(e.span)}"</a>`
             : `"${esc(e.span)}"`)
    : `<span class="muted">— sin span procesal</span>`;
  return `<li><span class="ev-fecha">${esc(e.fecha)}</span>${est}<span class="ev-span">${span}</span></li>`;
}

function tipoHTML(v) {
  return `<details class="tipo">
    <summary><span class="t-etq">${esc(v.etiqueta)}</span><span class="t-n">${v.n}</span></summary>
    <ul>${v.eventos.map(eventoTipoHTML).join("")}</ul>
  </details>`;
}

function delitoHTML(d) {
  const span = d.url
    ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">"${esc(d.span)}"</a>`
    : `"${esc(d.span)}"`;
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
      b1.tasa_alucinacion == null ? "pendiente del eval" : "Sistema vs Ablación"
    ),
  ].join("");

  const porCond = Object.entries(b1.eventos_por_condicion)
    .map(([c, n]) => `${COND[c]?.etq || c}: ${n}`).join(" · ");

  const disclaimer = b2.fuente_clasificacion === "gold_humano"
    ? "Tipos verificados por anotación humana (gold)."
    : "Categorización automática — auditable, no es un registro legal oficial.";

  const tipos   = Object.entries(b2.por_tipo).filter(([, v]) => v.n > 0).map(([, v]) => tipoHTML(v)).join("");
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
        <h3>Tipo procesal <span class="status-tag infer">inferencia del sistema</span></h3>
        <p class="disclaimer">${esc(disclaimer)}</p>
        <div class="tipos">${tipos}</div>
        <h4>Delitos / imputaciones mencionadas</h4>
        <ul class="delitos">${delitos}</ul>
      </div>
    </details>`;

  mostrar("resumen");
}

async function cargarResumen(slug) {
  try {
    const r = await fetch(`api/figuras/${slug}/resumen`);
    if (r.ok) renderResumen(await r.json());
  } catch { /* panel secundario — no bloquea */ }
}

// ── Carga de figura ───────────────────────────────────────────────────────────

async function cargarFigura(slug) {
  if (window.__vistaGrafo) return;   // en vista grafo, grafo.js maneja la carga
  const metaFigura = FIGURAS_META.find((f) => f.slug === slug);
  if (metaFigura?.tipo === "tema") {
    ocultar("cargando");
    ocultar("meta");
    ocultar("aviso");
    ocultar("resumen");
    ocultar("timeline");
    ocultar("vacio");
    ocultar("error");
    $("timeline").innerHTML = "";
    $("resumen").innerHTML  = "";
    requestAnimationFrame(() => $("vista-grafo").click());
    return;
  }
  // Estado de carga: solo el spinner visible
  mostrar("cargando");
  ocultar("meta");
  ocultar("aviso");
  ocultar("resumen");
  ocultar("timeline");
  ocultar("vacio");
  ocultar("error");
  $("timeline").innerHTML = "";
  $("resumen").innerHTML  = "";

  try {
    const r = await fetch(`api/figuras/${slug}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    FIGURA = await r.json();

    // Poblar selector de condición
    const condSel = $("condicion");
    condSel.innerHTML = FIGURA.condiciones.map((c) => {
      const m = COND[c] || { etq: c };
      return `<option value="${esc(c)}">${esc(m.etq)}</option>`;
    }).join("");

    // Preferir sistema_rag si tiene entradas
    const tieneRag   = FIGURA.eventos.some((e) => e.por_condicion.sistema_rag != null);
    CONDICION_ACTIVA = tieneRag ? "sistema_rag" : (FIGURA.condiciones[0] ?? "b1_extractive");
    condSel.value    = CONDICION_ACTIVA;

    // Ajustar rango de fechas
    const fechas = FIGURA.eventos.map((e) => e.fecha);
    if (fechas.length) {
      const min = fechas.reduce((a, b) => a < b ? a : b);
      const max = fechas.reduce((a, b) => a > b ? a : b);
      $("desde").min = $("hasta").min = min;
      $("desde").max = $("hasta").max = max;
      $("desde").value = min;
      $("hasta").value = max;
    }

    ocultar("cargando");
    mostrar("meta");
    mostrar("timeline");
    render();
    cargarResumen(slug);

  } catch (e) {
    ocultar("cargando");
    $("error").textContent = `No se pudo cargar la figura: ${e.message}`;
    mostrar("error");
  }
}

// ── Nueva figura ──────────────────────────────────────────────────────────────

async function recargarFiguras(seleccionar) {
  const figuras = await (await fetch("api/figuras")).json();
  FIGURAS_META = figuras;
  const sel = $("figura");
  sel.innerHTML = figuras.map((f) =>
    `<option value="${esc(f.slug)}">${esc(figuraLabel(f))}</option>`
  ).join("");
  if (seleccionar) sel.value = seleccionar;
  cargarFigura(sel.value);
}

function pollJob(slug, el) {
  const t = setInterval(async () => {
    try {
      const s   = await (await fetch(`api/jobs/${slug}`)).json();
      const log = (s.log || []).slice(-3).map(esc).join("<br>");
      if (s.estado === "running") {
        el.innerHTML = `<span class="spin">◴</span> Procesando <strong>${esc(slug)}</strong>…`
          + `<div class="joblog">${log}</div>`;
      } else if (s.estado === "done") {
        clearInterval(t);
        el.innerHTML = `✓ <strong>${esc(slug)}</strong> lista — cargando…`;
        await recargarFiguras(slug);
        ocultar("nueva");
      } else if (s.estado === "error") {
        clearInterval(t);
        el.innerHTML = `✗ Error: ${esc(s.error || "")}`;
      }
    } catch { /* reintenta en el próximo tick */ }
  }, 3000);
}

function initNueva() {
  $("btn-nueva").addEventListener("click", () => $("nueva").classList.toggle("oculto"));
  $("form-nueva").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const nombre = $("n-nombre").value.trim();
    if (!nombre) return;
    const split = (id) => $(id).value.split(",").map((s) => s.trim()).filter(Boolean);
    const el = $("n-estado");
    el.textContent = "Lanzando…";
    try {
      const r = await fetch("api/figuras", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ nombre, homonimos: split("n-homonimos"), terminos: split("n-terminos") }),
      });
      const s = await r.json();
      if (s.estado === "done") {
        el.innerHTML = `Ya existía — cargando…`;
        await recargarFiguras(s.slug);
        ocultar("nueva");
        return;
      }
      pollJob(s.slug, el);
    } catch (e) { el.textContent = "Error al lanzar: " + e.message; }
  });
}

// ── Modal fuentes ─────────────────────────────────────────────────────────────

function cerrarFuentes() {
  const modal = $("fuentes-modal");
  modal.classList.remove("abierto");
  modal.addEventListener("transitionend", () => {
    ocultar("fuentes-modal");
    document.body.style.overflow = "";
  }, { once: true });
}

function abrirFuentes(ev) {
  const d = new Date(ev.fecha + "T00:00:00");
  $("modal-titulo").textContent = fmtFecha.format(d);
  $("modal-n").textContent = `${ev.fuentes.length} fuente${ev.fuentes.length > 1 ? "s" : ""}`;

  $("modal-cuerpo").innerHTML = `<ol>${ev.fuentes.map(f => {
    const titulo = f.titulo || "(título no disponible)";
    const cabeza = f.url
      ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(titulo)}</a>`
      : `<strong>${esc(titulo)}</strong>`;
    const lead = f.lead ? `<p class="lead">${esc(f.lead)}</p>` : "";
    return `<li>${cabeza}${lead}<div class="docid">${esc(f.doc_id)}</div></li>`;
  }).join("")}</ol>`;

  mostrar("fuentes-modal");
  requestAnimationFrame(() => requestAnimationFrame(() =>
    $("fuentes-modal").classList.add("abierto")
  ));
  document.body.style.overflow = "hidden";
}

function initModal() {
  $("modal-cerrar").addEventListener("click", cerrarFuentes);
  $("fuentes-modal").addEventListener("click", e => {
    if (e.target === $("fuentes-modal")) cerrarFuentes();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && !$("fuentes-modal").classList.contains("oculto"))
      cerrarFuentes();
  });
  $("timeline").addEventListener("click", e => {
    const btn = e.target.closest(".btn-fuentes");
    if (!btn) return;
    const ev = _eventosActuales[parseInt(btn.dataset.idx)];
    if (ev) abrirFuentes(ev);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  initNueva();
  initModal();

  $("condicion").addEventListener("change", () => {
    CONDICION_ACTIVA = $("condicion").value;
    render();
  });
  ["desde", "hasta", "comparar"].forEach((id) => $(id).addEventListener("input", render));

  try {
    const figuras = await (await fetch("api/figuras")).json();
    FIGURAS_META = figuras;
    if (!figuras.length) {
      ocultar("cargando");
      $("error").textContent = `No hay figuras procesadas. Usa "+ Nueva figura" para crear una.`;
      mostrar("error");
      return;
    }
    const sel = $("figura");
    sel.innerHTML = figuras.map((f) =>
      `<option value="${esc(f.slug)}">${esc(figuraLabel(f))}</option>`
    ).join("");
    sel.addEventListener("change", () => cargarFigura(sel.value));
    cargarFigura(figuras[0].slug);
  } catch (e) {
    ocultar("cargando");
    $("error").textContent = `No se pudo conectar con el backend: ${e.message}`;
    mostrar("error");
  }
}

init();
