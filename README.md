# PLN - Consulta de Perfiles

Proyecto NLP en espanol para analizar noticias politicas peruanas. Tiene dos usos principales:

- **Cronologias de figuras politicas**: genera lineas de tiempo comparando cuatro condiciones: `B0Lead`, `B1Extractive`, `SistemaRAG` y `Ablacion`.
- **Grafos temporales de relaciones**: construye grafos de entidades y relaciones abiertas desde un corpus Andina/JSONL, con una arista fechada por co-ocurrencia.

La aplicacion web FastAPI **solo lee resultados ya precomputados**. No debe scrapear, correr spaCy/torch ni llamar LLMs durante un request.

## Requisitos

- Python `>=3.12,<3.14`. La version local sugerida esta en `.python-version`: `3.13`.
- `uv` para crear el entorno y ejecutar comandos del proyecto.
- Modelo spaCy espanol `es_core_news_md` para NER y dependency parsing en los flujos locales.
- `.env` solo si vas a usar LLMs o cambiar configuracion por entorno. Los flujos B0/B1 y `build_open_graph.py` no requieren API key.

## Instalacion

Desde la raiz del repositorio:

```bash
uv sync
uv run python -m spacy download es_core_news_md
```

Opcional, si vas a usar LLMs o quieres fijar variables de entorno:

```bash
cp .env.example .env
```

En Windows PowerShell usa:

```powershell
copy .env.example .env
```

Verifica el entorno:

```bash
uv run python -c "import pandas, spacy; spacy.load('es_core_news_md'); print('OK')"
```

## Ejecutar La App Web

Las salidas finales versionadas viven en `data/salidas/` y `data/figuras.json`, asi que no necesitas reprocesar nada para abrir la aplicacion.

```bash
uv run uvicorn src.app.api:app --reload
```

Abre `http://127.0.0.1:8000`.

La app lee:

- `data/figuras.json`
- `data/salidas/<slug>/*.json`
- `data/corpus_<slug>.parquet`, si existe, para resolver fuentes
- `data/graph_<slug>.duckdb`, si existe, para la vista de grafo

## Construir Un Grafo Temporal Desde JSONL

Si ya tienes `data/andina_crawl.jsonl`, puedes construir un grafo temporal de relaciones abiertas sin LLM ni API key.

Ejemplo para marzo-mayo de 2026, inclusivo:

```bash
uv run python scripts/build_open_graph.py andina-mar-may-2026 \
  --jsonl data/andina_crawl.jsonl \
  --top-n 300 \
  --inicio 03-2026 \
  --fin 05-2026
```

Esto lee `data/andina_crawl.jsonl` y escribe:

```text
data/graph_andina-mar-may-2026.duckdb
```

Notas importantes:

- `--inicio` y `--fin` usan formato `MM-YYYY`; el rango es inclusivo por mes completo.
- El script carga el corpus, filtra fechas, filtra idioma espanol, descubre entidades, extrae predicados abiertos y guarda el grafo en DuckDB.
- Si `data/graph_<slug>.duckdb` ya existe, el script lo borra y lo reconstruye.
- `--wikidata` es opcional y agrega llamadas de red para enriquecer entidades.
- `--menciones` solo aplica al leer un corpus parquet con `--corpus-slug`; no se usa con `--jsonl`.
- Por defecto usa `es_core_news_md` porque el script fija `SPACY_NER_MODEL` y `SPACY_DEP_MODEL` si no estan definidos.

Tambien puedes construir desde un corpus parquet existente:

```bash
uv run python scripts/build_open_graph.py grafo-humala \
  --corpus-slug humala \
  --top-n 40 \
  --inicio 03-2026 \
  --fin 05-2026
```

## Crear `data/andina_crawl.jsonl` Si No Existe

El crawler por ID de Andina es resumible, pero puede ser lento porque visita una URL por ID. Usa rangos acotados.

```bash
uv run python scripts/crawl_andina.py \
  --desde-id <ID_INICIO> \
  --hasta-id <ID_FIN> \
  --salida data/andina_crawl.jsonl \
  --delay 0.5 \
  --desde 2026-03-01 \
  --hasta 2026-05-31
```

El checkpoint queda junto al JSONL:

```text
data/andina_crawl.ckpt.json
```

Reanudar es volver a correr el mismo comando.

## Otros Flujos Offline

Regenerar una figura configurada en `src/figuras.py`:

```bash
uv run python scripts/precompute_figura.py humala
```

Este flujo escribe `data/corpus_<slug>.parquet`, `data/salidas/<slug>/*.json`, `data/graph_<slug>.duckdb` y actualiza `data/figuras.json`. Sin API key genera solo `b0_lead.json` y `b1_extractive.json`; con LLM disponible tambien genera `sistema_rag.json` y `ablacion.json`.

Construir un grafo de tema configurado en `src/figuras.py`:

```bash
uv run python scripts/precompute_tema.py elecciones-2021-2026
```

`precompute_tema.py` reutiliza `data/corpus_<slug>.parquet` si existe; si no, scrapea las fuentes configuradas. Tambien borra `data/graph_<slug>.duckdb` si existe para hacer un rerun limpio.

Frontend Streamlit legacy, si lo necesitas:

```bash
uv run streamlit run src/app/streamlit_app.py
```

Debe estar corriendo el backend FastAPI.

## Entradas Y Salidas

Entradas frecuentes:

- `.env`: proveedor LLM, API keys opcionales, modelos spaCy, `TIMELINE_DATA_DIR`.
- `src/figuras.py`: figuras, temas, queries, ventanas temporales, gazetteers y homonimos.
- `data/andina_crawl.jsonl`: corpus JSONL producido por el crawler.
- `data/corpus_<slug>.parquet`: corpus preprocesado por figura/tema.
- `data/figuras.json`: manifiesto que consume la app.
- `data/salidas/<slug>/*.json`: cronologias precomputadas.
- `data/graph_<slug>.duckdb`: grafo precomputado.
- `annotation/gold/`, `annotation/gold_relaciones/`, `annotation/gold_entidades/`: datos gold para evaluacion.

Salidas frecuentes:

- `data/figuras.json`: manifiesto de figuras/temas disponibles.
- `data/salidas/<slug>/*.json`: salidas de cronologia por condicion.
- `data/corpus_<slug>.parquet`: corpus descargado/preprocesado.
- `data/graph_<slug>.duckdb`: grafo DuckDB de relaciones.
- `data/andina_crawl.jsonl`: crawl completo o parcial de Andina.
- `data/andina_crawl.ckpt.json`: checkpoint del crawler.
- `data/jobs/<slug>.json`, `data/jobs/<slug>.log`, `data/jobs/<slug>.params.json`: jobs lanzados desde la web.
- `data/figuras_dinamicas.json`: figuras creadas desde la UI.

Los archivos intermedios grandes bajo `data/` suelen estar gitignoreados. Las salidas finales versionadas son `data/figuras.json` y `data/salidas/`.

## Variables De Entorno Importantes

- `RELATIONS_LLM_PROVIDER`: proveedor compartido para clasificacion de relaciones y generacion de timeline (`anthropic`, `openai`, `groq`, `gemini`). Sin `.env`, el codigo usa `anthropic`; `.env.example` usa `gemini`.
- `RELATIONS_LLM_MODEL` / `TIMELINE_LLM_MODEL`: override de modelos.
- `RELATIONS_LLM_TEMPERATURE`: default `0.0`.
- `TIMELINE_LLM_TEMPERATURE`: default `0.7`.
- `SPACY_NER_MODEL`: modelo spaCy para NER; localmente usa `es_core_news_md`.
- `SPACY_DEP_MODEL`: modelo spaCy para dependency parsing; localmente usa `es_core_news_md`.
- `TIMELINE_DATA_DIR`: raiz de datos para grafos y cache. Debe fijarse antes de importar `src.storage` o `src.app.api` en tests que usen un directorio temporal.
- `RELATIONS_NLP_PROCS`: procesos para `nlp.pipe` en extraccion de relaciones abiertas; default `1`.

## Verificacion Y Checks

No hay suite pytest configurada, CI, pre-commit, Makefile ni task runner. Usa checks focalizados:

```bash
uv run python -m compileall -q src scripts eval
uv run python scripts/test_relations.py
uv run python scripts/test_entities.py
uv run python scripts/test_multifuente.py
uv run python scripts/test_eval.py
uv run python scripts/test_grafo_api.py
uv run python scripts/test_relation_typing.py
```

La evaluacion completa de cronologias requiere gold congelado:

```bash
uv run python -m eval.run_experiment 3
```

Los CSV de evaluacion de relaciones y entidades viven bajo `annotation/gold_relaciones/` y `annotation/gold_entidades/`.
