# Resultados — Clasificación de relaciones entre entidades políticas

*Proyecto T02 (Generación de lenguaje / PLN) — enfoque tema-céntrico.*
*Estado: resultados preliminares (gold de un solo anotador, pendiente de acuerdo
inter-anotador; ver §5 y `annotation/GUIA_ANOTACION.md`).*

---

## 1. Pregunta y enfoque

Dado un **tema político y un rango de fechas**, descubrir las entidades relevantes
(personas, partidos, instituciones) de un corpus de noticias y **tipificar las
relaciones entre ellas** para construir un grafo de conocimiento interpretable. La
pregunta de NLP medible de este informe es:

> ¿Con qué calidad se puede **clasificar automáticamente el tipo de relación**
> entre dos entidades co-ocurrentes en una oración, y qué método lo logra?

Taxonomía de 7 relaciones: `alianza`, `conflicto`, `pertenencia`, `nombramiento`,
`acusacion`, `ruptura`, `mencion` (co-aparición sin relación clara).

## 2. Metodología

**Corpus.** Figura/tema `roberto-sanchez`: 850 notas de la Agencia Andina,
ventana 2021–2026. Backbone compartido: NER (spaCy `es_core_news_md`) →
descubrimiento de entidades → co-ocurrencias por oración → clasificación de
relaciones → grafo (DuckDB + NetworkX).

**Descubrimiento de entidades.** Agrupación de menciones por contención de tokens;
filtro consciente de tipo (se retienen actores **PER+ORG**, se descartan
LOC/MISC y un denylist de genéricos), aplicado *antes* del corte top-N.

**Clasificadores de relación comparados** (mismo input, `Coocurrencia`):
- **Reglas** — lexicón de verbos sobre el triple del dep-parse. Sin LLM.
- **Híbrido** — reglas primero; escala al LLM si la confianza de reglas < 0.65.
- **LLM** — Claude Haiku (`anthropic`), juzga la relación entre las dos entidades.

**Gold.** Muestra estratificada por tipo sugerido, exportada con
`scripts/export_relaciones_gold.py` y etiquetada a mano según
`annotation/GUIA_ANOTACION.md`. Entidades: 55 nodos etiquetados; relaciones: 135
oraciones. **Convención central:** la relación debe darse *entre las dos entidades
del par*; si no (lista, encuesta, byline, enlace erróneo), es `mencion`.

**Métricas.** Entidades: precisión/recall de "actor", exactitud de tipo, splits.
Relaciones: accuracy, macro-F1 y P/R/F1 por tipo (matriz de confusión).

## 3. Resultados

### 3.1 Resolución de entidades (n=55; 34 retenidas por el filtro)

| métrica | valor | lectura |
|---|---|---|
| actor_precision | **0.71** | ~30 % de lo retenido es ruido (bylines de redacción tipados ORG) |
| actor_recall | **0.83** | el filtro descartó ~17 % de actores reales (ministerios mal tipados; "Poder Ejecutivo" en el denylist) |
| type_accuracy | **0.67** | el NER mis-tipa ~1/3 (p. ej. ministerios como LOC) |
| splits | **2** | "Min. de Comercio Exterior y Turismo" y "Betssy Chávez" partidos en 2 nodos |

### 3.2 Clasificación de relaciones (n=135)

| | reglas | híbrido | **LLM** |
|---|---|---|---|
| **accuracy** | 0.274 | 0.252 | **0.748** |
| **macro-F1** | 0.285 | 0.283 | **0.577** |
| `mencion` (R) | 0.18 | 0.13 | **0.76** |
| `conflicto` (F1) | 0.62 | 0.59 | **0.74** |
| `acusacion` (F1) | 0.41 | 0.45 | **0.70** |
| `pertenencia` (F1) | 0.20 | 0.26 | **0.56** |
| `nombramiento` (F1) | 0.09 | 0.08 | 0.43† |
| `alianza` (F1) | 0.09 | 0.08 | 0.20† |

† soporte insuficiente (`nombramiento` n=3, `alianza` n=2): no concluyentes.

**Resultado principal:** el LLM **casi triplica el accuracy (0.27 → 0.75)** y
duplica el macro-F1 (0.29 → 0.58) frente a reglas, sobre los mismos 135 ejemplos.

## 4. Análisis de error (mecanismo)

1. **Co-ocurrencia ≠ relación.** El 74 % del gold (100/135) es `mencion`: dos
   entidades aparecen en la misma oración (listas de candidatos, encuestas,
   bancadas, créditos de redacción) sin una relación entre *ellas*.
2. **Las reglas sobre-disparan relaciones tipadas.** `mencion` recall = **0.18**:
   de 100 co-menciones reales solo detecta 18; las demás las marca como
   alianza/nombramiento/pertenencia porque hay un verbo-gatillo en la oración,
   aunque ese verbo no conecte a las dos entidades.
3. **El híbrido por umbral no corrige el fallo.** Solo escaló 20/135 al LLM y su
   accuracy (0.252) es igual a reglas. Razón: escala cuando la confianza de
   reglas es *baja*, pero **los errores de reglas son de alta confianza**
   (lista marcada como nombramiento con 0.82). El umbral está mal calibrado para
   el modo de fallo real.
4. **El LLM resuelve la atribución.** `mencion` recall **0.18 → 0.76**: el LLM
   entiende cuándo la oración no expresa relación entre las dos entidades dadas.
   Es el motor del salto de accuracy.
5. **Bylines contaminan el grafo de entidades** (actor_precision 0.71): las líneas
   de crédito ("NDP/JCR Publicado: fecha") se tipan como ORG y entran como nodos.

## 5. Amenazas a la validez

- **Un solo anotador.** El gold lo etiquetó una persona; las métricas se miden
  contra ese criterio. Acción en curso: convenciones explícitas
  (`annotation/GUIA_ANOTACION.md`) + acuerdo inter-anotador sobre una muestra
  (`scripts/acuerdo_anotadores.py`) antes de reportar números definitivos.
- **Sensibilidad a la convención.** Decisiones discutibles afectan el número:
  rivalidad de segunda vuelta etiquetada `mencion` (no `conflicto`); co-acusados
  etiquetados `acusacion`. Si cambian, parte de los "errores" del LLM se
  reclasifican. (⚠ a decidir con el responsable.)
- **Soporte insuficiente** para `alianza` (n=2) y `nombramiento` (n=3): reportar
  como no concluyentes, no como debilidad del método. Requieren más gold.
- **Generalización.** Un solo corpus/figura (roberto-sanchez). Replicar en otra
  figura/tema antes de generalizar.

## 6. Decisiones de diseño derivadas

1. **Clasificar relaciones con el LLM.** El costo es irrelevante: el precómputo
   agrupa por **par único de entidades** (~123 llamadas por grafo, no por
   oración). Se decide por calidad.
2. **Rediseñar el híbrido según el modo de fallo medido:** confiar en reglas
   *solo* cuando predicen `mencion` (donde su precisión es 0.90–1.00) y enviar al
   LLM toda predicción *tipada* (lo no fiable). Es un resultado en sí, no solo
   ahorro: el rediseño se justifica por el diagnóstico (errores de alta confianza
   que el umbral no atrapaba).
3. **Limpiar bylines en preprocess** (líneas "XXX/YYY Publicado: fecha") para
   subir actor_precision.
4. **Sacar "ejecutivo" del denylist** y evaluar **NER transformer** para reducir
   el mis-tipado de instituciones (sube actor_recall y type_accuracy).

## 7. Próximos pasos

1. Fijar convenciones (hecho, v1) → acuerdo inter-anotador sobre ≥30 filas →
   recoger números finales.
2. Aplicar el híbrido rediseñado en `precompute_tema.py` y regenerar el grafo.
3. Ampliar gold para los tipos con poco soporte.
4. Replicar en una segunda figura/tema.

---

### Apéndice — Reproducibilidad

```bash
# Gold (export estratificado) y evaluación
uv run python scripts/export_relaciones_gold.py roberto-sanchez --n 140
uv run python -m eval.relations annotation/gold_relaciones/roberto-sanchez.csv          # reglas
uv run python -m eval.relations annotation/gold_relaciones/roberto-sanchez.csv --llm    # reglas vs híbrido vs LLM
uv run python -m eval.entities  annotation/gold_entidades/roberto-sanchez.csv           # resolución de entidades

# Acuerdo inter-anotador
uv run python scripts/acuerdo_anotadores.py --blank annotation/gold_relaciones/roberto-sanchez.csv --n 30
uv run python scripts/acuerdo_anotadores.py annotation/gold_relaciones/roberto-sanchez.csv <B>.csv --col tipo_gold
```

Entorno: Claude Haiku vía `RELATIONS_LLM_PROVIDER=anthropic`; temperatura 0.7;
variación entre corridas inherente (sin semilla de generación).
