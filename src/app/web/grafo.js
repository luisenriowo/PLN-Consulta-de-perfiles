"use strict";
// Vista de GRAFO de relaciones (Fase 4). Independiente del timeline (app.js):
// comparte el selector #figura y el rango #desde/#hasta, y se activa/desactiva
// con window.__vistaGrafo (app.js hace bail cuando está activa).
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const TIPOS = {
    alianza:      { etq: "Alianza",      color: "#2e7d32" },
    conflicto:    { etq: "Conflicto",    color: "#c62828" },
    pertenencia:  { etq: "Pertenencia",  color: "#1565c0" },
    nombramiento: { etq: "Nombramiento", color: "#6a1b9a" },
    acusacion:    { etq: "Acusación",    color: "#e65100" },
    ruptura:      { etq: "Ruptura",      color: "#ad1457" },
    mencion:      { etq: "Mención",      color: "#9e9e9e" },
  };
  const NODO_COLOR = { PER: "#1e88e5", ORG: "#fb8c00", LOC: "#43a047", MISC: "#757575" };

  const fmt = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", year: "numeric" });
  const fday = (iso) => iso ? fmt.format(new Date(String(iso).slice(0, 10) + "T00:00:00")) : "—";

  let cy = null, SLUG = null, ENTIDADES = [], RELACIONES = [];
  let activos = new Set();           // tipos de relación visibles
  let minConf = 0;

  // ── Datos ───────────────────────────────────────────────────────────────────
  const entById = () => Object.fromEntries(ENTIDADES.map((e) => [e.entity_id, e]));

  function relsFiltradas() {
    const d = $("desde").value, h = $("hasta").value;
    return RELACIONES.filter((r) => {
      const f = String(r.fecha).slice(0, 10);
      return activos.has(r.tipo) && (r.confianza ?? 0) >= minConf
        && (!d || f >= d) && (!h || f <= h);
    });
  }

  function elementos() {
    const rels = relsFiltradas();
    const usados = new Set();
    rels.forEach((r) => { usados.add(r.origen_id); usados.add(r.destino_id); });
    const E = entById();
    const nodos = [...usados].filter((id) => E[id]).map((id) => {
      const e = E[id];
      return { data: {
        id, nombre: e.nombre, tipo: e.tipo,
        color: NODO_COLOR[e.tipo] || "#757575",
        size: 18 + Math.sqrt((e.n_docs || 1)) * 2.4,
      } };
    });
    const aristas = rels.map((r) => ({ data: {
      id: "e" + r.id, relId: r.id, source: r.origen_id, target: r.destino_id,
      tipo: r.tipo, tipoEtq: TIPOS[r.tipo]?.etq || r.tipo,
      color: TIPOS[r.tipo]?.color || "#9e9e9e",
      width: 1.2 + (r.confianza ?? 0.5) * 3,
    } }));
    return { nodos, aristas, nRels: rels.length };
  }

  // ── Render del grafo ──────────────────────────────────────────────────────────
  const ESTILO = [
    { selector: "node", style: {
        "background-color": "data(color)", "label": "data(nombre)",
        "width": "data(size)", "height": "data(size)",
        "font-size": 9, "color": "#1a1a1a", "text-valign": "center",
        "text-halign": "center", "text-wrap": "wrap", "text-max-width": 78,
        "text-outline-color": "#fff", "text-outline-width": 1.5,
    } },
    { selector: "edge", style: {
        "line-color": "data(color)", "target-arrow-color": "data(color)",
        "target-arrow-shape": "triangle", "curve-style": "bezier",
        "width": "data(width)", "label": "data(tipoEtq)",
        "font-size": 7, "color": "#666", "text-rotation": "autorotate",
        "text-background-color": "#fff", "text-background-opacity": 0.8,
        "text-background-padding": 1,
    } },
    { selector: ".sel", style: { "line-color": "#111", "target-arrow-color": "#111", "width": 4, "z-index": 99 } },
    { selector: ".sel-node", style: { "border-width": 3, "border-color": "#111" } },
    { selector: ".dim", style: { "opacity": 0.18 } },
  ];

  function dibujar() {
    const { nodos, aristas, nRels } = elementos();
    $("g-stats").textContent = `${nodos.length} entidades · ${nRels} relaciones`;
    if (!cy) {
      cy = cytoscape({ container: $("cy"), style: ESTILO, wheelSensitivity: 0.2,
        elements: [...nodos, ...aristas] });
      cy.on("tap", "edge", (ev) => panelArista(ev.target));
      cy.on("tap", "node", (ev) => panelNodo(ev.target));
      cy.on("tap", (ev) => { if (ev.target === cy) limpiarSel(); });
    } else {
      cy.batch(() => { cy.elements().remove(); cy.add([...nodos, ...aristas]); });
    }
    cy.layout({ name: "cose", animate: false, padding: 30, nodeRepulsion: 9000,
      idealEdgeLength: 90, nodeDimensionsIncludeLabels: true }).run();
  }

  function limpiarSel() {
    if (cy) cy.elements().removeClass("sel sel-node dim");
  }

  // ── Panel: evidencia de una arista ─────────────────────────────────────────────
  async function panelArista(edge) {
    limpiarSel();
    cy.elements().addClass("dim");
    edge.removeClass("dim").addClass("sel");
    edge.source().removeClass("dim"); edge.target().removeClass("dim");
    const d = edge.data();
    const cab = `<div class="gp-edge">
      <h3>${esc(edge.source().data("nombre"))} <span class="gp-arrow">→</span> ${esc(edge.target().data("nombre"))}</h3>
      <p class="gp-tipo" style="--c:${d.color}"><span class="gp-dot"></span>${esc(d.tipoEtq)}</p>
      <p class="gp-cargando">cargando evidencia…</p></div>`;
    $("grafo-panel").innerHTML = cab;
    try {
      const r = await fetch(`api/figuras/${SLUG}/grafo/relaciones/${d.relId}/evidencia`);
      const ev = await r.json();
      const pasajes = (ev.pasajes || []).map((p) => `<li>${esc(p)}</li>`).join("")
        || `<li class="muted">— sin pasajes</li>`;
      const fuentes = (ev.fuentes || []).map((f) => {
        const t = f.titulo || f.doc_id;
        const a = f.url ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(t)}</a>` : esc(t);
        return `<li>${a}<span class="gp-docid">${esc(f.doc_id)}</span></li>`;
      }).join("");
      $("grafo-panel").querySelector(".gp-cargando").outerHTML =
        `<h4>Evidencia</h4><ul class="gp-pasajes">${pasajes}</ul>
         <h4>Fuentes (${(ev.fuentes || []).length})</h4><ol class="gp-fuentes">${fuentes}</ol>`;
    } catch (e) {
      const el = $("grafo-panel").querySelector(".gp-cargando");
      if (el) el.textContent = "No se pudo cargar la evidencia.";
    }
  }

  // ── Panel: relaciones de un nodo, en el tiempo (vista derivada) ─────────────────
  function panelNodo(node) {
    limpiarSel();
    cy.elements().addClass("dim");
    node.removeClass("dim").addClass("sel-node");
    node.connectedEdges().removeClass("dim").addClass("sel");
    node.neighborhood("node").removeClass("dim");
    const id = node.id(), E = entById();
    const rels = relsFiltradas()
      .filter((r) => r.origen_id === id || r.destino_id === id)
      .sort((a, b) => String(a.fecha).localeCompare(String(b.fecha)));
    const filas = rels.map((r) => {
      const saliente = r.origen_id === id;
      const otro = saliente ? r.destino_nombre : r.origen_nombre;
      const flecha = saliente ? "→" : "←";
      const c = TIPOS[r.tipo]?.color || "#9e9e9e";
      return `<li><span class="gp-fecha">${esc(fday(r.fecha))}</span>
        <span class="gp-badge" style="--c:${c}">${esc(TIPOS[r.tipo]?.etq || r.tipo)}</span>
        <span class="gp-rel">${esc(flecha)} ${esc(otro)}</span></li>`;
    }).join("") || `<li class="muted">— sin relaciones en el filtro actual</li>`;
    const e = E[id] || {};
    $("grafo-panel").innerHTML = `<div class="gp-node">
      <h3>${esc(node.data("nombre"))}</h3>
      <p class="gp-meta">${esc(e.tipo || "")} · ${e.n_docs || 0} notas · ${rels.length} relaciones</p>
      <h4>Relaciones en el tiempo</h4>
      <ul class="gp-rels">${filas}</ul></div>`;
  }

  // ── Controles ───────────────────────────────────────────────────────────────
  function chips() {
    const presentes = [...new Set(RELACIONES.map((r) => r.tipo))]
      .sort((a, b) => Object.keys(TIPOS).indexOf(a) - Object.keys(TIPOS).indexOf(b));
    activos = new Set(presentes);
    $("g-tipos").innerHTML = presentes.map((t) =>
      `<button class="chip activo" data-tipo="${esc(t)}" style="--c:${TIPOS[t]?.color || "#999"}">
        <span class="chip-dot"></span>${esc(TIPOS[t]?.etq || t)}</button>`).join("");
  }

  function panelReset() {
    $("grafo-panel").innerHTML = `<p class="gp-hint">Clic en un <strong>nodo</strong> para ver
      sus relaciones en el tiempo, o en una <strong>arista</strong> para la evidencia.</p>`;
  }

  // ── Carga ──────────────────────────────────────────────────────────────────────
  async function cargarGrafo() {
    SLUG = $("figura").value;
    if (!SLUG) return;
    $("grafo-msg").classList.add("oculto");
    if (!window.cytoscape) {
      msg("No se pudo cargar la librería de grafos (¿sin conexión a internet?).");
      return;
    }
    try {
      const [re, rr] = await Promise.all([
        fetch(`api/figuras/${SLUG}/grafo/entidades`),
        fetch(`api/figuras/${SLUG}/grafo/relaciones`),
      ]);
      if (re.status === 404 || rr.status === 404) {
        msg(`Esta figura no tiene grafo todavía. Genéralo con:  python scripts/precompute_tema.py ${SLUG}`);
        return;
      }
      ENTIDADES = await re.json();
      RELACIONES = await rr.json();
      if (!RELACIONES.length) { msg("El grafo no tiene relaciones tipadas."); return; }
      chips();
      panelReset();
      dibujar();
    } catch (e) {
      msg("Error al cargar el grafo: " + e.message);
    }
  }

  function msg(texto) {
    $("g-stats").textContent = "";
    $("grafo-panel").innerHTML = "";
    if (cy) { cy.destroy(); cy = null; }
    $("cy").innerHTML = "";
    const m = $("grafo-msg"); m.textContent = texto; m.classList.remove("oculto");
  }

  // ── Conmutador de vista ─────────────────────────────────────────────────────
  const TIMELINE_IDS = ["meta", "aviso", "resumen", "timeline", "vacio", "ctl-condicion", "ctl-comparar"];

  function mostrarVista(grafo) {
    window.__vistaGrafo = grafo;
    $("vista-grafo").classList.toggle("activo", grafo);
    $("vista-timeline").classList.toggle("activo", !grafo);
    TIMELINE_IDS.forEach((id) => { const el = $(id); if (el) el.classList.toggle("oculto", grafo); });
    $("grafo-vista").classList.toggle("oculto", !grafo);
    if (grafo) {
      cargarGrafo();
    } else {
      // volver al timeline: app.js recarga al disparar 'change' del selector
      $("figura").dispatchEvent(new Event("change"));
    }
  }

  function init() {
    $("vista-grafo").addEventListener("click", () => mostrarVista(true));
    $("vista-timeline").addEventListener("click", () => mostrarVista(false));
    // Recargar el grafo al cambiar de figura (solo si la vista grafo está activa)
    $("figura").addEventListener("change", () => { if (window.__vistaGrafo) cargarGrafo(); });
    // Filtros que comparten controles con el timeline (no hacen nada si no está activa)
    ["desde", "hasta"].forEach((id) => $(id).addEventListener("input", () => {
      if (window.__vistaGrafo && cy) dibujar();
    }));
    $("g-conf").addEventListener("input", () => {
      minConf = parseFloat($("g-conf").value);
      $("g-conf-val").textContent = minConf.toFixed(2);
      if (cy) dibujar();
    });
    $("g-tipos").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      const t = chip.dataset.tipo;
      if (activos.has(t)) { activos.delete(t); chip.classList.remove("activo"); }
      else { activos.add(t); chip.classList.add("activo"); }
      if (cy) dibujar();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
