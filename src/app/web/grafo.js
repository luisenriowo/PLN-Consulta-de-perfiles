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
    // Relación abierta (OpenIE) — cuando `tipo = null` y `predicado != null`.
    __abierta__:  { etq: "Abierta",      color: "#607d8b" },
  };
  const NODO_COLOR = { PER: "#1e88e5", ORG: "#fb8c00", LOC: "#43a047", MISC: "#757575" };

  // ── Helpers para relaciones abiertas (tipo null + predicado) ──────────────
  const relTipoKey = (r) => r.tipo || "__abierta__";
  const relEtiqueta = (r) => r.predicado || r.tipo || "Relación abierta";
  const relColor = (r) => TIPOS[relTipoKey(r)]?.color || "#607d8b";
  const relTipoEtq = (r) => TIPOS[relTipoKey(r)]?.etq || relEtiqueta(r);

  const fmt = new Intl.DateTimeFormat("es", { day: "numeric", month: "short", year: "numeric" });
  const fday = (iso) => iso ? fmt.format(new Date(String(iso).slice(0, 10) + "T00:00:00")) : "—";

  let cy = null, SLUG = null, ENTIDADES = [], RELACIONES = [];
  let activos = new Set();           // tipos de relación visibles
  let minConf = 0;
  // Estado P4 — modo de selección de dos entidades para ver su evolución
  let MODO_EVOLUCION = false;
  let evolucionA = null;              // primer nodo seleccionado en el modo
  let debounceBuscar = null;

  // ── Datos ───────────────────────────────────────────────────────────────────
  const entById = () => Object.fromEntries(ENTIDADES.map((e) => [e.entity_id, e]));

  function relsFiltradas() {
    const d = $("desde").value, h = $("hasta").value;
    return RELACIONES.filter((r) => {
      const f = String(r.fecha).slice(0, 10);
      return activos.has(relTipoKey(r)) && (r.confianza ?? 0) >= minConf
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
      tipo: relTipoKey(r),
      tipoEtq: r.predicado || relTipoEtq(r),   // A3: predicado abierto si existe
      predicado: r.predicado || null,
      color: relColor(r),
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
      cy.on("tap", "node", (ev) => onNodeTap(ev.target));
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

  // ── Panel: evidencia de una arista + evolución del par ───────────────────────────
  async function panelArista(edge) {
    limpiarSel();
    cy.elements().addClass("dim");
    edge.removeClass("dim").addClass("sel");
    edge.source().removeClass("dim"); edge.target().removeClass("dim");
    const d = edge.data();
    const etiqueta = d.predicado || d.tipoEtq;   // A3: predicado si existe
    const cab = `<div class="gp-edge">
      <h3>${esc(edge.source().data("nombre"))} <span class="gp-arrow">→</span> ${esc(edge.target().data("nombre"))}</h3>
      <p class="gp-tipo" style="--c:${d.color}"><span class="gp-dot"></span>${esc(etiqueta)}</p>
      ${d.predicado ? `<p class="gp-pred">predicado: <code>${esc(d.predicado)}</code></p>` : ""}
      <p class="gp-cargando">cargando evidencia…</p></div>`;
    $("grafo-panel").innerHTML = cab;
    const srcId = edge.source().id(), dstId = edge.target().id();
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
    // Sección evolución del par — siempre, incluso si el modo evolución está activo
    await cargarEvolucionPar(srcId, dstId);
  }

  async function cargarEvolucionPar(aId, bId) {
    let cont = $("grafo-panel").querySelector(".gp-evolucion");
    if (!cont) {
      $("grafo-panel").insertAdjacentHTML("beforeend",
        `<div class="gp-evolucion"><h4>Evolución del par</h4><p class="gp-ev-vacio">cargando…</p></div>`);
      cont = $("grafo-panel").querySelector(".gp-evolucion");
    }
    try {
      const r = await fetch(`api/figuras/${SLUG}/grafo/evolucion?entidad_a=${encodeURIComponent(aId)}&entidad_b=${encodeURIComponent(bId)}`);
      if (!r.ok) { cont.querySelector(".gp-ev-vacio").textContent = "No se pudo cargar la evolución del par."; return; }
      const payload = await r.json();
      cont.innerHTML = `<h4>Evolución del par</h4>` + renderEvolucion(payload);
    } catch (e) {
      cont.querySelector(".gp-ev-vacio").textContent = "No se pudo cargar la evolución del par.";
    }
  }

  function renderEvolucion(payload) {
    const evs = payload.eventos || [];
    if (!evs.length) return `<p class="gp-ev-vacio">No hay relaciones entre estas entidades en el filtro actual.</p>`;
    const E = entById();
    const aId = (payload.entidad_a || {}).entity_id;
    const bId = (payload.entidad_b || {}).entity_id;
    return `<ul class="gp-rels">` + evs.map((e) => {
      const saliente = e.origen_id === aId;
      const flecha = saliente ? "→" : "←";
      const color = relColor(e);
      return `<li class="gp-ev-item">
        <span class="gp-fecha">${esc(fday(e.fecha))}</span>
        <span class="gp-badge" style="--c:${color}">${esc(e.predicado || relTipoEtq(e))}</span>
        <span class="gp-flecha">${flecha}</span>
        <span class="gp-rel">${esc(saliente ? (payload.entidad_b||{}).nombre : (payload.entidad_a||{}).nombre)}</span>
        <span class="gp-conf">${(e.confianza ?? 0).toFixed(2)}</span></li>`;
    }).join("") + `</ul>`;
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
      const c = relColor(r);
      const etiqueta = r.predicado || relTipoEtq(r);   // A3: predicado si existe
      return `<li><span class="gp-fecha">${esc(fday(r.fecha))}</span>
        <span class="gp-badge" style="--c:${c}">${esc(etiqueta)}</span>
        <span class="gp-rel">${esc(flecha)} ${esc(otro)}</span></li>`;
    }).join("") || `<li class="muted">— sin relaciones en el filtro actual</li>`;
    const e = E[id] || {};
    $("grafo-panel").innerHTML = `<div class="gp-node">
      <h3>${esc(node.data("nombre"))}</h3>
      <p class="gp-meta">${esc(e.tipo || "")} · ${e.n_docs || 0} notas · ${rels.length} relaciones</p>
      <h4>Relaciones en el tiempo</h4>
      <ul class="gp-rels">${filas}</ul></div>`;
  }

  // ── P4: tap de nodo con modo evolución ───────────────────────────────────────
  function onNodeTap(node) {
    if (MODO_EVOLUCION) {
      const id = node.id();
      if (evolucionA === null) {
        evolucionA = id;
        limpiarSel();
        node.addClass("sel-node");
        actualizarEstadoEvolucion("Selecciona una segunda entidad distinta");
      } else if (id === evolucionA) {
        actualizarEstadoEvolucion("Selecciona una segunda entidad distinta");
      } else {
        const a = evolucionA, b = id;
        evolucionA = null;
        actualizarEstadoEvolucion("Cargando evolución…");
        panelEvolucion(a, b).finally(() => actualizarEstadoEvolucion(null));
      }
      return;
    }
    panelNodo(node);
  }

  function actualizarEstadoEvolucion(txt) {
    $("g-evolucion-estado").textContent = txt || "";
  }

  async function panelEvolucion(aId, bId) {
    limpiarSel();
    const E = entById();
    const a = E[aId] || { nombre: aId }, b = E[bId] || { nombre: bId };
    $("grafo-panel").innerHTML =
      `<div class="gp-node"><h3>Evolución: ${esc(a.nombre)} ↔ ${esc(b.nombre)}</h3>
       <p class="gp-cargando">cargando…</p></div>`;
    try {
      const r = await fetch(`api/figuras/${SLUG}/grafo/evolucion?entidad_a=${encodeURIComponent(aId)}&entidad_b=${encodeURIComponent(bId)}`);
      if (!r.ok) {
        $("grafo-panel").querySelector(".gp-cargando").textContent =
          r.status === 404 ? "Una de las entidades no existe." : "No se pudo cargar la evolución.";
        return;
      }
      const payload = await r.json();
      $("grafo-panel").innerHTML =
        `<div class="gp-node">
           <h3>${esc(payload.entidad_a.nombre)} ↔ ${esc(payload.entidad_b.nombre)}</h3>
           <p class="gp-meta">${(payload.eventos || []).length} eventos · bidireccional</p>
           <h4>Evolución del par</h4>
           ${renderEvolucion(payload)}
         </div>`;
    } catch (e) {
      const el = $("grafo-panel").querySelector(".gp-cargando");
      if (el) el.textContent = "No se pudo cargar la evolución.";
    }
  }

  function toggleModoEvolucion() {
    MODO_EVOLUCION = !MODO_EVOLUCION;
    const btn = $("g-modo-evolucion");
    btn.classList.toggle("activo", MODO_EVOLUCION);
    evolucionA = null;
    if (cy) cy.elements().removeClass("sel-node");
    if (MODO_EVOLUCION) {
      actualizarEstadoEvolucion("Selecciona primera entidad");
      panelResetEvolucion();
    } else {
      actualizarEstadoEvolucion(null);
      panelReset();
    }
  }

  function panelResetEvolucion() {
    $("grafo-panel").innerHTML = `<div class="gp-node">
      <h3>Modo evolución</h3>
      <p class="gp-hint">Haz clic en un nodo para fijar la <strong>primera entidad</strong>,
      luego en otro para ver la <strong>evolución temporal</strong> del par.</p></div>`;
  }

  // ── P4: búsqueda de entidades con debounce ───────────────────────────────
  async function buscarEntidades(q) {
    const cont = $("g-resultados");
    if (q === null) { cont.innerHTML = ""; return; }
    try {
      const r = await fetch(`api/figuras/${SLUG}/grafo/entidades/buscar?q=${encodeURIComponent(q)}&limit=20`);
      if (!r.ok) { cont.innerHTML = ""; return; }
      const lista = await r.json();
      renderResultados(lista);
    } catch (e) {
      cont.innerHTML = "";
    }
  }

  function renderResultados(lista) {
    const cont = $("g-resultados");
    if (!Array.isArray(lista) || !lista.length) { cont.innerHTML = ""; return; }
    cont.innerHTML = lista.map((e) => {
      const tipo = e.tipo || "MISC";
      return `<div class="g-res-item" data-eid="${esc(e.entity_id)}">
        <span class="g-res-nombre">${esc(e.nombre)} <span class="g-res-tipo ${esc(tipo)}">${esc(tipo)}</span></span>
        <span class="g-res-meta">${e.n_docs || 0} docs</span>
      </div>`;
    }).join("");
  }

  async function cargarEgo(entityId, profundidad = 1) {
    if (!entityId) return;
    if (debounceBuscar) { clearTimeout(debounceBuscar); debounceBuscar = null; }
    $("g-resultados").innerHTML = "";
    $("grafo-msg").classList.add("oculto");
    $("grafo-panel").innerHTML = `<p class="gp-cargando">cargando ego-grafo…</p>`;
    try {
      const r = await fetch(`api/figuras/${SLUG}/grafo/ego/${encodeURIComponent(entityId)}?profundidad=${profundidad}`);
      if (!r.ok) {
        msg(`No se pudo cargar el ego-grafo (HTTP ${r.status}).`);
        return;
      }
      const payload = await r.json();
      ENTIDADES = payload.entidades || [];
      RELACIONES = payload.relaciones || [];
      if (!RELACIONES.length) {
        msg("El ego-grafo no tiene relaciones tipadas.");
        $("g-tipos").innerHTML = "";    // A5: limpiar chips del grafo anterior
        return;
      }
      chips();
      panelReset();
      const e0 = (ENTIDADES.find((x) => x.entity_id === entityId) || {});
      $("g-stats").textContent = `ego · ${ENTIDADES.length} entidades · ${RELACIONES.length} relaciones`
        + (payload.truncado ? " · (truncado)" : "");
      $("grafo-panel").innerHTML = `<div class="gp-node">
        <h3>${esc(e0.nombre || entityId)}</h3>
        <p class="gp-meta">Ego-grafo · ${e0.tipo || ""} · ${(e0.n_docs||0)} notas · ${RELACIONES.length} relaciones</p>
        <p class="gp-hint">Clic en una <strong>arista</strong> para evidencia + evolución del par,
        o activa <strong>Modo evolución</strong> para elegir dos nodos.</p></div>`;
      dibujar();
    } catch (e) {
      msg("Error al cargar el ego-grafo: " + e.message);
    }
  }

  function verGrafoCompleto() {
    if (MODO_EVOLUCION) toggleModoEvolucion();
    cargarGrafo();
  }

  // ── Controles ───────────────────────────────────────────────────────────────
  function chips() {
    const presentes = [...new Set(RELACIONES.map(relTipoKey))]
      .sort((a, b) => Object.keys(TIPOS).indexOf(a) - Object.keys(TIPOS).indexOf(b));
    // A4: preservar selección previa del usuario (intersección con presentes).
    const prev = activos;
    activos = new Set(presentes.filter((t) => prev.has(t)));
    if (activos.size === 0) activos = new Set(presentes);  // si ninguno coincide, activar todos
    $("g-tipos").innerHTML = presentes.map((t) =>
      `<button class="chip ${activos.has(t) ? "activo" : ""}" data-tipo="${esc(t)}" style="--c:${TIPOS[t]?.color || "#999"}">
        <span class="chip-dot"></span>${esc(TIPOS[t]?.etq || t)}</button>`).join("");
  }

  function panelReset() {
    $("grafo-panel").innerHTML = `<p class="gp-hint">Clic en un <strong>nodo</strong> para ver
      sus relaciones en el tiempo, o en una <strong>arista</strong> para la evidencia.</p>`;
  }

  // ── Carga ──────────────────────────────────────────────────────────────────────
  const UMBRAL_COMPLETO = 2000;  // si n_relaciones > umbral, no cargar completo

  async function cargarGrafo() {
    SLUG = $("figura").value;
    if (!SLUG) return;
    // Reset estado P4 al (re)cargar grafo completo
    if (MODO_EVOLUCION) toggleModoEvolucion();
    $("g-buscar").value = "";
    $("g-resultados").innerHTML = "";
    $("grafo-msg").classList.add("oculto");
    if (!window.cytoscape) {
      msg("No se pudo cargar la librería de grafos (¿sin conexión a internet?).");
      return;
    }
    try {
      // Primero pedir stats para decidir si cargar todo o sólo búsqueda.
      const rs = await fetch(`api/figuras/${SLUG}/grafo/stats`);
      if (rs.status === 404) {
        msg(`Esta figura no tiene grafo todavía. Genéralo con:  python scripts/precompute_tema.py ${SLUG}`);
        return;
      }
      if (!rs.ok) { msg("No se pudo verificar el tamaño del grafo."); return; }
      const stats = await rs.json();
      $("g-stats").textContent = `${stats.n_entidades} entidades · ${stats.n_relaciones} relaciones`;

      if (stats.n_relaciones > UMBRAL_COMPLETO) {
        // Grafo grande: no cargar completo, sólo búsqueda/ego.
        ENTIDADES = []; RELACIONES = [];
        if (cy) { cy.destroy(); cy = null; }
        $("grafo-panel").innerHTML = `<div class="gp-hint">
          <h3>Grafo grande (${stats.n_relaciones} relaciones)</h3>
          <p>Este grafo es demasiado grande para mostrar completo de forma eficiente.
          Usa la <strong>búsqueda</strong> para encontrar una entidad y cargar su
          <strong>ego-grafo</strong>.</p>
          <p class="gp-meta">${stats.n_entidades} entidades · ${stats.n_relaciones} relaciones
          · ${stats.fecha_min || "—"} a ${stats.fecha_max || "—"}</p></div>`;
        $("g-tipos").innerHTML = "";
        return;
      }

      // Grafo pequeño: cargar completo (entidades + relaciones).
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
  window.__mostrarVistaGrafo = mostrarVista;

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

    // ── P4: nuevos controles
    $("g-buscar").addEventListener("input", (e) => {
      const q = e.target.value.trim();
      if (debounceBuscar) clearTimeout(debounceBuscar);
      if (!q) { $("g-resultados").innerHTML = ""; return; }
      debounceBuscar = setTimeout(() => buscarEntidades(q), 280);
    });
    $("g-buscar").addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.target.value = ""; $("g-resultados").innerHTML = ""; }
    });
    $("g-resultados").addEventListener("click", (e) => {
      const it = e.target.closest(".g-res-item");
      if (!it) return;
      const eid = it.dataset.eid;
      cargarEgo(eid, 1);
    });
    $("g-ver-todo").addEventListener("click", verGrafoCompleto);
    $("g-modo-evolucion").addEventListener("click", toggleModoEvolucion);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
