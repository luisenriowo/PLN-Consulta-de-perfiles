# Hallazgos — Backbone NLP a escala y grafo abierto-temporal

*Proyecto T02 (Generación de lenguaje / PLN) — dirección full-archive / relaciones
abiertas tipadas después.*
*Estado: hallazgos metodológicos y cualitativos sobre el corpus `andina-v1`. La
evaluación cuantitativa (precisión de entidades, de triples abiertos y de tipado)
espera el etiquetado de los golds + acuerdo inter-anotador (ver §6 y
`annotation/GUIA_ANOTACION.md`).*

---

## 1. Montaje

**Corpus.** `andina-v1`: snapshot congelado de **11.311 notas en español** de la
Agencia Andina (crawl por ID 2021-2026, filtradas por idioma), con manifiesto +
sha256 (`data/corpus_andina_v1.manifest.json`). NER persistido: **376.846
menciones** (`data/menciones_corpus_andina_v1/`).

**Pipeline a escala.** crawl por ID → consolidación (dedup + bylines + filtro de
idioma) → NER transformer (GPU) → resolución de entidades con *blocking* →
extracción de relaciones **abiertas** fechadas → grafo temporal (DuckDB) →
tipado **inducido** (clustering de predicados). Producto: `graph_andina-v1.duckdb`
(**150 entidades, 93.032 aristas abiertas fechadas**).

## 2. NER a escala (→ §Método)

- **Modelo.** Los modelos NER españoles de PlanTL/BSC (`roberta-base-bne-capitel-ner`)
  están **gated** (HTTP 401) y no son usables sin credenciales. Se adoptó
  `mrm8488/bert-spanish-cased-finetuned-ner` (BETO afinado en CoNLL-2002).
- **Límite de 512 tokens.** Las notas exceden la ventana del modelo. Se ventanea
  **por oraciones** (empaque ≤512 tok, corte por caracteres como respaldo) y se
  **filtran fragmentos subword** (`##`), que el pipeline emite en los bordes.
- **GPU.** torch `cu128` (RTX 4070 SUPER); ~36 docs/s. Las menciones se
  **persisten** (parquet chunked, reanudable) para no re-NERizar en cada build.
- **Para el paper:** comparar md/lg/transformer en una muestra con gold (ablación
  NER, F6) — pendiente; aquí se documenta la *viabilidad* del transformer a escala.

## 3. Resolución de entidades (→ §Método + §Resultados)

- **Blocking.** La agrupación por contención de tokens es O(n²) sobre menciones;
  con un **índice token→grupos** se reduce a O(menciones×candidatos):
  **376.846 menciones → actores en ~53 s**.
- **Filtro actor + fragmentos.** Se retienen PER+ORG, se descartan genéricos
  (denylist) y **fragmentos de NER** (`_es_fragmento`: token corto no-MAYÚSCULA,
  p. ej. "And", "Ma", "Pro"; se conservan acrónimos como OMS, ONP, APP). El filtro
  va **antes** del corte top-N.
- **HALLAZGO — sobre-fusión por tokens comunes.** La contención de tokens **fusiona
  entidades distintas que comparten un token frecuente**: el nodo "Policía Nacional
  del Perú" absorbió "Ministerio de Salud del Perú" (token "del Perú"/"Salud"),
  "Jurado Nacional de Elecciones" absorbió "Tribunal Constitucional" (token
  "Nacional"/"Pleno"), "República" absorbió "Alianza para el Progreso". Es el modo
  de error dominante de la resolución a escala; lo cuantificará el gold de entidades
  (`type_accuracy`, inspección de alias). **Mitigación propuesta:** exigir contención
  de los tokens **distintivos** (cabeza nominal), no de cualquiera.

## 4. Relaciones abiertas (→ §Método)

- **HALLAZGO — el *matching* por substring explota el grafo.** Detectar la mención
  de una entidad en una oración por substring (`nombre in oracion`) hace que
  **nombres cortos casen dentro de otras palabras** ("Ma" ⊂ "Lima"/"programa"),
  generando co-ocurrencias falsas masivas (un par fragmento~fragmento llegó a
  **25.749 aristas**). El *fix* —match por **límite de palabra** (`\b…\b`)— bajó el
  grafo de **378.908 → 127.986 aristas** sin perder relaciones reales. *Lección
  metodológica:* a escala, el reconocimiento de menciones necesita límites de token.
- **DECISIÓN — predicado *precision-first* (co-ocurrencia ≠ relación).** El extractor
  de predicado tenía un *fallback* a "cualquier verbo de la oración" cuando el verbo
  conector estaba vetado → emitía aristas con verbos que **no conectan a las dos
  entidades**, reintroduciendo el error central del proyecto. Se eliminó: solo se
  emite arista si un verbo **conecta a A y B** en el árbol de dependencias o es la
  **acción raíz** de la oración. Efecto: **162.581 → 93.032 aristas**, más limpias.
- **HALLAZGO — precisión de la extracción abierta < 1.** En una muestra del grafo,
  muchas co-ocurrencias muestreadas no son relación entre el par (ONPE~El Peruano en
  una oración sobre Minsa; JNE~Muni. Lima sin vínculo) y aparecen **artefactos de
  lema** del modelo `md` ("coordinir" por *coordina*, "incidir al"). El **gold OpenIE**
  (`triple_valido_gold`, `predicado_ok_gold`) cuantificará esto; la historia esperada
  es **alto recall / precisión moderada** en extracción, que el tipado/filtro mejora.

## 5. Tipado inducido (→ §Método + §Resultados)

- **HALLAZGO técnico — clusterizar PREDICADOS, no aristas.** Embeber/clusterizar una
  vez por arista no escala: 93.032 aristas → matriz de distancias O(n²) ≈ 8.6·10⁹ →
  *MemoryError*. La solución es clusterizar los **predicados únicos** (6.703) y mapear
  cada arista a su cluster. (Para v2/full-archive, agglomerativo O(n²) tampoco escala
  más allá de ~15-20k predicados → considerar MiniBatchKMeans/HDBSCAN.)
- **Umbral.** Con el template `"ENT_A predicado ENT_B"`, los embeddings son muy
  similares; `distance_threshold=0.35` **colapsa todo en un mega-cluster**. Barrido
  (predicados ≥5 apariciones, 2.929 cubren 92,1% de aristas):

  | umbral | nº clusters | mayor cluster (% aristas) |
  |---|---|---|
  | 0.05 | 636 | 7,6 % |
  | 0.08 | 369 | 27 % |
  | **0.10** | 245 | 49 % |
  | 0.12 | 171 | 65 % |
  | 0.20 | 38 | 95 % (colapsa) |

  Se fijó **0.10** por defecto (454 clusters sobre el set completo, 61 con ≥200
  aristas).
- **HALLAZGO — a escala, la relación típica es una ACCIÓN GENÉRICA, no la taxonomía
  política.** El cluster mayor (~46 % de las aristas) reúne verbos genéricos
  (proponer, aprobar, recibir, ofrecer, realizar). Los clusters **distintivos** sí
  emergen coherentes y nombrables: *participar/asistir*, *supervisar/liderar/presidir*,
  *recomendar/apoyar/contribuir*, *reportar/denunciar*, *pedir/solicitar*,
  *fortalecer/reforzar/mejorar*, *implementar/ejecutar*, *confirmar*, *exhortar*,
  *concluir/finalizar*. **Implicación:** una taxonomía fija de 7 tipos políticos no
  cubre un corpus general; el tipado inducido revela que la mayoría de vínculos son
  acciones administrativas/operativas y solo una minoría son relaciones políticas
  tipables. Esto justifica la decisión de **extraer abierto y tipar después**.

## 6. Grafo temporal (→ §Análisis)

- El multigrafo temporal **reconstruye la evolución de un par** a escala: JNE~ONPE
  tiene **9.490 aristas fechadas** (2021→2026); `evolucion(a,b)` las devuelve
  ordenadas (sancionar → se reunir → ofrecer → clasificar → advertir …). Los pares
  más densos son institucionales y plausibles (JNE~ONPE, Policía Nacional~ONPE,
  MINSA~MINCETUR), coherentes con el ciclo electoral 2021.

## 7. Artefactos de evaluación preparados (→ §Evaluación)

Golds listos para etiquetado humano (4 anotadores) sobre `andina-v1`:
- `annotation/gold_entidades/andina-v1.csv` — 80 entidades (63 retenidas) →
  `eval/entities` (actor P/R, type accuracy, splits/merges).
- `annotation/gold_relaciones_abiertas/andina-v1.csv` — 160 triples →
  `eval/openie` (precisión de triple y de predicado) + tipo sugerido.
- `data/salidas/andina-v1/relation_type_clusters.csv` — 454 clusters →
  `eval/relation_typing` (etiquetar `tipo_label`; coherencia/cobertura).

**Pendiente (corazón del paper):** etiquetado + **κ de Cohen** sobre ≥60 filas
(`scripts/acuerdo_anotadores.py`) antes de reportar números.

## 8. Amenazas a la validez (a escala)

- **Fuente única estatal (Andina).** Sesgo institucional/oficial; el modelo
  `multi_fuente` está listo pero el corpus v1 es mono-fuente.
- **Notas en inglés.** El servicio en inglés de Andina se mezcla; se filtra por
  idioma (`es_espanol`) — validar el filtro.
- **Calidad del dep-parse (`md`).** Artefactos de lema y caminos rotos afectan al
  predicado; evaluar `lg`/transformer-dep es trabajo futuro.
- **Gold de un solo anotador / pendiente de IAA** (igual que en
  `resultados-relaciones.md`).

---

### Apéndice — Reproducibilidad
```bash
# Grafo abierto-temporal v1 (reusa NER persistido)
uv run python scripts/build_open_graph.py andina-v1 --corpus-slug andina_v1 --menciones --top-n 150
# Golds
uv run python scripts/export_entidades_gold.py andina-v1 --corpus-slug andina_v1 --menciones --top 80
uv run python scripts/export_openie_gold.py andina-v1 --n 160
uv run python scripts/export_relation_type_clusters.py andina-v1   # umbral 0.10
```
