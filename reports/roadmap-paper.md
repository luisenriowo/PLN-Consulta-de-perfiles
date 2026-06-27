# Roadmap (tipo paper / workshop) — Grafo temporal de relaciones abiertas en noticias peruanas

*Curso, con exigencia estilo workshop/conferencia de NLP. Leyenda: ✅ hecho · 🟡 parcial · ⬜ pendiente.*

Decisiones fijadas con el equipo:
- **Contribuciones (4)**: recurso/dataset, método/hallazgo, sistema/demo, análisis político.
  - *Recomendación de framing*: **liderar con recurso + método**; sistema (demo) y
    análisis (casos) como secciones de apoyo. Un paper de workshop no sostiene 4
    contribuciones co-iguales.
- **Tipado de relaciones**: **inducido** (clustering de predicados → tipos emergentes),
  coherente con "todos los temas".
- **Acuerdo inter-anotador**: *decisión del autor* → **se planifica un 2º anotador sobre
  una muestra** (≥60 ítems estratificados) para κ de Cohen. Fallback si no hay 2º:
  convenciones explícitas + re-anotación intra-anotador con separación temporal, y
  reportarlo como limitación.
- **Venue**: estilo workshop (rigor de revisión por pares), entregable de curso.

---

## 0. Marco del paper

**Preguntas de investigación**
- **RQ1** (método/recurso): ¿se puede construir un grafo TEMPORAL de relaciones entre
  entidades desde un archivo COMPLETO de noticias con extracción ABIERTA (sin taxonomía
  previa) y tipado POSTERIOR inducido, y con qué calidad por componente?
- **RQ2** (hallazgo): ¿cuánto mejora la atribución de relaciones un LLM frente a
  reglas? (co-ocurrencia ≠ relación; medido: 0.27 → 0.75 accuracy).
- **RQ3** (tipado inducido): ¿qué tipos de relación EMERGEN del corpus multi-tema y qué
  tan interpretables/estables son?
- **RQ4** (análisis): ¿qué revela la evolución temporal de relaciones entre actores
  2021-2026?

**Contribuciones declaradas**
1. **Recurso**: corpus Andina 2021-2026 + grafo temporal de relaciones abiertas + gold
   anotado, liberados (con datasheet).
2. **Método**: pipeline OpenIE → tipado inducido, a escala de archivo completo,
   evaluado por componente.
3. **Hallazgo**: co-ocurrencia ≠ relación; el LLM resuelve la atribución (0.27→0.75);
   el híbrido por umbral falla (errores de alta confianza).
4. **Sistema** (demo): explorador temporal (búsqueda, ego-grafo, evolución de un par).
5. **Análisis**: casos de evolución de relaciones entre actores.

**Estructura objetivo (IMRaD, ~8 pp.)**: Abstract · Introducción · Trabajo relacionado ·
Datos · Método · Evaluación · Resultados · Análisis/Casos + Demo · Limitaciones y Ética ·
Conclusión.

---

## F1 · Recurso / Corpus  → §Datos
- 🟡 Crawl completo 2021-2026 por ID (`scripts/crawl_andina.py`, reanudable). **Falta** terminarlo.
- ⬜ Limpieza a escala: dedup (firma), **filtro de idioma** (`es_espanol`, validar), bylines (✅).
- ⬜ Normalización temporal: decidir `fecha_pub` (DCT) vs resolver fechas del texto; justificar.
- ⬜ **Snapshot congelado** + hash + fecha de crawl (reproducibilidad).
- ⬜ **Estadísticas descriptivas** (tabla): nº notas, notas/mes, longitud, % por tema, % EN descartado.
- ⬜ **Datasheet** (origen, recolección, ética, usos).

## F2 · Backbone NLP a escala  → §Método
- 🟡 **NER**: spaCy md (dev). **Falta**: comparar md/lg/transformer y reportar; batch a escala.
- 🟡 **Resolución de entidades**: contención + filtro actor (PER+ORG) + Wikidata.
  **Falta**: dedup de QIDs, coref básica, escalar (blocking), evaluar (gold de entidades).
- ✅ **Extracción de relaciones ABIERTAS** (OpenIE-lite, dep-path) + modelo TEMPORAL
  (arista fechada por co-ocurrencia, no colapsa; `extraer_relaciones_abiertas`, `build_open_graph.py`).
- ⬜ **Mejorar el predicado**: filtrar verbos de reporte (dijo/señaló), capturar frase
  (verbo+preposición), lematizar; evaluar precisión de la extracción.

## F3 · Tipado INDUCIDO de relaciones  → §Método + §Resultados
- ⬜ **Embedding de predicados** (frase/verbo) + **clustering** → tipos emergentes.
- ⬜ **Etiquetado humano de clusters** (nombrar cada cluster con un tipo interpretable).
- ⬜ **Mapeo arista→tipo** vía su cluster; persistir `tipo` (hoy nullable en el schema).
- ⬜ **Evaluación**: coherencia de clusters, cobertura, y gold de tipos (P/R/F1).
- ✅ **Comparación reglas vs LLM** (ruta política, 135 ej.): 0.27 → 0.75. → §Resultados/hallazgo.
- ⬜ **(opcional) LLM on-demand** para tipar al explorar (escala con la exploración, no el corpus).

## F4 · Grafo temporal + análisis  → §Análisis/Casos
- ✅ Grafo temporal abierto (validado: 40 ent / 5573 aristas fechadas; evolución de pares).
- ⬜ **Red**: centralidad (PageRank) + comunidades (Louvain) globales y por ventana; precomputar.
- ⬜ **Evolución**: detección de cambios de relación (p. ej. alianza→conflicto) en el tiempo.
- ⬜ **Casos de estudio interpretados** (el autor propone/interpreta) → narrativa del paper.

## F5 · Sistema / Explorador (demo)  → §Demo
- 🟡 Web timeline + grafo (figura única). **Falta para escala**: búsqueda de entidad,
  **ego-grafo on-demand**, **vista de evolución** del par (timeline de predicados),
  filtros temporales server-side, paginación.
- ⬜ Endpoints: search entidad, ego-grafo(entidad, prof., ventana), evolución(par).

## F6 · Evaluación + Gold + IAA  → §Evaluación (corazón del paper)
- 🟡 Golds existentes: relaciones (135) y entidades (55), **1 anotador**.
- ⬜ **Gold de relaciones abiertas** (precisión de triples) y **gold de tipos inducidos**.
- ⬜ **2º anotador sobre muestra (≥60) + κ de Cohen** (`acuerdo_anotadores.py` ✅).
- ⬜ **Arneses**: relaciones ✅, entidades ✅; **falta** OpenIE y tipado.
- ⬜ **Baselines/ablaciones**: reglas vs LLM (✅); ±filtro actor; ±bylines; NER md/transformer;
  tipos fijos vs inducidos; co-ocurrencia vs relación.
- ⬜ **Validación humana** de una muestra; **análisis de error** (borrador en reports/).

## F7 · Rigor, reproducibilidad, ética, limitaciones  → §Limitaciones/Ética
- 🟡 Repro: LLM temp 0.0 + modelo fijo (✅). **Falta**: congelar versiones (spaCy/modelos/corpus),
  semillas, script de reproducción end-to-end.
- ⬜ **Costos LLM**: arreglar `_llm.costo()` (lee proveedor de generación, no el de relaciones).
- ⬜ **Ética**: robots.txt (✅); personas en contextos judiciales (atribución, no afirmar hechos);
  **sesgo de fuente única ESTATAL (Andina)**; sesgos del LLM.
- ⬜ **Limitaciones**: una agencia, español, profundidad temporal, OpenIE superficial.

## F8 · Escritura  → todo el paper
- ⬜ **Trabajo relacionado**: OpenIE, extracción de relaciones/eventos, *temporal KG*,
  NLP político/de noticias, NLP en español, construcción de KG.
- ⬜ Método · Datos · Experimentos · Resultados (tablas/figuras) · Análisis · Limitaciones ·
  Ética · Conclusión · Abstract+Intro.
- 🟡 Borrador de resultados de relaciones en `reports/resultados-relaciones.md`.
- ⬜ **Figuras**: pipeline, ejemplo de grafo, curva de evolución de una relación, tablas.
- ⬜ **Artefactos liberados**: corpus, grafo, gold, código (repro).

## Transversal
- ⬜ Versionado dataset/modelo; tests (✅ varios) a escala; **actualizar CLAUDE.md** (atrás del modelo abierto-temporal).

---

## Ruta crítica recomendada (secuencia)

1. **Terminar el crawl** (F1) — es el cuello de botella; corre en paralelo a todo.
2. **Backbone a escala** (F2): NER batch + resolución de entidades + extracción abierta sobre el corpus completo.
3. **Tipado inducido** (F3): clustering de predicados → tipos emergentes → etiquetar clusters.
4. **Gold + IAA** (F6) sobre el corpus real: entidades, relaciones abiertas, tipos; 2º anotador + κ.  ← *no posponer; el número del paper depende de esto.*
5. **Análisis** (F4) + **Demo** (F5) sobre el grafo completo.
6. **Escritura** (F8) en paralelo desde el paso 3 (volcar resultados cuando estén frescos).

## División de trabajo (4 personas)

División por **componente** con interfaces fijas (contratos) para paralelizar.
Cada persona es **dueña de su sección del paper**. Asignar por fortalezas; rebalanceable.

### P1 — Datos & Infraestructura (*Data Lead*)
- **F1**: terminar/operar el crawl, limpieza a escala, filtro de idioma, **snapshot
  congelado + hash**, estadísticas descriptivas, **datasheet**.
- **F7**: reproducibilidad (congelar versiones spaCy/modelos, semillas, script
  end-to-end), arreglar `_llm.costo()`.
- **Paper**: §Datos, §Reproducibilidad, parte de §Ética (recolección/sesgo de fuente).
- **Provee a todos**: el corpus congelado. **Entrega temprana clave**: una *semilla
  congelada* (slice acotado o el corpus roberto-sanchez) en la semana 1 para que P2/P3/P4
  no esperen al crawl completo.

### P2 — Backbone NLP: NER + Entidades
- **F2**: comparar NER (md/lg/transformer), **resolución de entidades a escala**
  (dedup QID, coref básica, blocking), filtro actor.
- **F6 (parte)**: gold + evaluación de **entidades** (actor P/R, type accuracy, splits).
- **Paper**: §Método (NER+entidades), §Resultados (entidades).
- **Depende de** P1 (corpus). **Provee a** P3 y P4 (entidades canónicas).
- **Contrato**: `EntityNode` + tabla `entities` (fijos).

### P3 — Relaciones abiertas + Tipado inducido + Hallazgo (*Research Lead*)
- **F2/F3**: mejorar extracción abierta (filtrar verbos de reporte, frase, lematizar),
  **tipado inducido** (embedding de predicados → clustering → etiquetar clusters →
  persistir `tipo`).
- **Hallazgo** reglas vs LLM (0.27→0.75, ya medido) + ablaciones.
- **F6 (parte)**: gold + eval de **relaciones** (abiertas + tipos), análisis de error.
- **Paper**: §Método (relaciones/tipado), §Resultados (hallazgo + tipos), §Análisis de error.
- **Depende de** P2 (entidades). **Provee a** P4 (grafo tipado).
- **Contrato**: `RelationEdge` (predicado, tipo, fecha) + tabla `relations` (fijos).
- **Coordina** la integración del paper.

### P4 — Grafo temporal, Sistema/Demo & Análisis (*Product/Analysis Lead*)
- **F4**: grafo temporal a escala, **red** (centralidad/comunidades por ventana),
  detección de **evolución** de relaciones.
- **F5**: explorador a escala (búsqueda de entidad, **ego-grafo on-demand**, **vista de
  evolución del par**, filtros temporales), endpoints.
- **F4 análisis**: casos de estudio interpretados (preguntas de Erasmo).
- **Paper**: §Análisis/Casos, §Demo/Sistema.
- **Depende de** P3 (grafo) y P2 (entidades). **Contrato**: API de lectura del grafo.

### Transversal (los 4)
- **Anotación / IAA**: los 4 anotan la **misma muestra (~60 ítems)** → κ de Cohen
  (resuelve el riesgo del anotador único); además cada uno anota una porción disjunta
  para cobertura. Convenciones en `annotation/GUIA_ANOTACION.md`.
- **Escritura**: cada quien su sección; P3 integra; revisión cruzada.

### Interfaces fijas (para no bloquearse)
| Contrato | Dueño | Consumidores |
|---|---|---|
| Corpus JSONL (`doc_id,fuente,url,fecha_pub,texto`) | P1 | P2 |
| `EntityNode` + tabla `entities` | P2 | P3, P4 |
| `RelationEdge` (predicado/tipo/fecha) + tabla `relations` | P3 | P4 |
| API de lectura del grafo (entidades, relaciones, evolución, ego-grafo) | P4 | demo, análisis |

### Secuencia para paralelizar
- **Semana 1**: P1 entrega **semilla congelada**; los 4 fijan contratos y convenciones de anotación.
- **Paralelo**: P2 (entidades) → P3 (relaciones/tipado) sobre la semilla; P4 monta demo/análisis
  sobre el grafo de la semilla; P1 completa el crawl en background.
- **Integración**: al llegar el corpus completo, re-correr el pipeline (P1→P2→P3→P4) y
  recoger números finales + gold/IAA.

## Riesgos y mitigaciones
- *Crawl largo (~días)* → reanudable; empezar análisis en una ventana mientras completa.
- *Predicados ruidosos* → filtrado de verbos de reporte + clustering agrupa el ruido.
- *Gold de un solo anotador* → 2º anotador sobre muestra + κ (decidido).
- *Sesgo de fuente única* → declararlo como limitación; (futuro) multi-fuente (GDELT ya integrado).
- *4 contribuciones dispersas* → liderar con recurso+método; demo/análisis de apoyo.
