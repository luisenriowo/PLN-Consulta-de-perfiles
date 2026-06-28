# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project overview

`timeline-gen` is a NLP research pipeline (T02 — Generación de lenguaje) that builds political-figure timelines from a Spanish news corpus (Agencia Andina primary, GDELT secondary). It compares four generation conditions — B0Lead, B1Extractive, SistemaRAG, Ablación — on the **same** backbone-produced event clusters, then serves the results via a FastAPI + static-web backend.

**Topic-centric pivot (in progress).** The project is moving from figure-centric
timelines to a **topic-centric entity-relation graph**: given a *topic + date
range*, it discovers ~10–20 entities (people, parties, institutions) from the
corpus and builds a typed relation graph between them. The graph is the product;
a figure's timeline becomes a *derived view* (the ego-network of one node). The
graph backbone (`pipeline/entity_discovery.py`, `pipeline/relations.py`,
`pipeline/relation_classifier.py`, `storage/graph.py`) is built and exposed via
`/api/figuras/{slug}/grafo/*`; the topic orchestrator is
`scripts/precompute_tema.py`. See "Topic-centric pipeline" below.

**Full-archive / open-temporal direction (current target).** Beyond a single
topic, the project is scaling to a **complete crawl of Andina 2021-2026, all
topics** (by ID enumeration, `scripts/crawl_andina.py`), and to **open relations
typed later**: instead of classifying into a fixed taxonomy at extraction time,
it extracts the **free connecting verb** between two entities (OpenIE-lite,
`relations.relacion_abierta`) and keeps **one dated edge per co-occurrence** (a
**temporal multigraph** — the same pair has many dated edges, so a relationship's
**evolution** over time is reconstructable via `graph.evolucion`). Types are
*induced later* (predicate clustering). Builder: `scripts/build_open_graph.py`.
The relation goal is now a general knowledge-graph explorer, not only a focused
political graph. Plan: `reports/roadmap-paper.md`. See "Open-temporal relations".

## Commands

```bash
# Install (from repo root, activate .venv first)
pip install -e .
python -m spacy download es_core_news_md    # dev/smoke
python -m spacy download es_core_news_lg    # production NER (precompute)

# Run backend (serves http://127.0.0.1:8000 + static web frontend)
uvicorn src.app.api:app --reload

# Run Streamlit frontend (legacy; requires backend up)
streamlit run src/app/streamlit_app.py

# Offline precompute a figure (slug must exist in src/figuras.py)
python scripts/precompute_figura.py <slug>      # e.g. humala, keiko, roberto-sanchez

# Offline precompute a TOPIC graph (slug in TEMAS in src/figuras.py, or reuse an
# existing figure's corpus by passing its slug). Builds data/graph_<slug>.duckdb.
python scripts/precompute_tema.py <slug>        # e.g. elecciones-2021-2026, humala
# Fully offline run (no Wikidata, rules-only relations):
WIKIDATA_ENRIQUECER=0 ANTHROPIC_API_KEY= python scripts/precompute_tema.py <slug>

# Build Humala corpus from scratch (scraping + NER + gate-metrics)
python scripts/build_corpus.py

# Run generation only (reads existing corpus_humala.parquet)
python scripts/run_generation.py

# Evaluate: 4 conditions × N runs (requires gold in annotation/gold/)
python -m eval.run_experiment [N]

# Validate eval harness with known-answer fixtures (no gold needed)
python scripts/test_eval.py

# Relation classifier evaluation (topic-centric headline metric)
python scripts/export_relaciones_gold.py <slug> [--n 140]   # → annotation/gold_relaciones/<slug>.csv (fill tipo_gold by hand)
python -m eval.relations annotation/gold_relaciones/<slug>.csv [--llm]   # P/R/F1 per relation type
python scripts/test_relations.py            # validate the relation harness with known-answer fixtures (no gold/network)

# Entity resolution evaluation (graph node quality)
python scripts/export_entidades_gold.py <slug> [--top 60]   # → annotation/gold_entidades/<slug>.csv (fill es_actor_gold, tipo_correcto, nombre_canonico)
python -m eval.entities annotation/gold_entidades/<slug>.csv   # actor precision/recall, type accuracy, splits
python scripts/test_entities.py             # validate the entity harness with known-answer fixtures (no gold/network)
python scripts/test_multifuente.py          # validate multi-source layer (multi_fuente signal, cross-source dedup, collector dispatch)

# Full Andina crawl by ID (all topics, 2021-2026; resumable via checkpoint)
python scripts/crawl_andina.py --desde-id 825000 --hasta-id 1100000 \
  --salida data/andina_crawl.jsonl --delay 0.4 --desde 2021-01-01 --hasta 2026-12-31
# Build the TEMPORAL OPEN-relation graph from a corpus (jsonl crawl or parquet)
python scripts/build_open_graph.py <slug> --jsonl data/andina_crawl.jsonl --top-n 300
python scripts/build_open_graph.py <slug> --corpus-slug <otro> --top-n 40   # reuse a parquet corpus

# Smoke test ingest (lightweight, no full scrape)
python scripts/smoke_ingest.py
```

Environment variables (in a `.env` file, gitignored):
- `RELATIONS_LLM_PROVIDER` — proveedor LLM: `anthropic` | `openai` | `groq` | `gemini` (default: `anthropic`). Governa tanto la clasificación de relaciones como la generación de timeline. Cambiar aquí es suficiente para migrar de proveedor sin tocar código.
- API key del proveedor elegido — solo se necesita para SistemaRAG y Ablación; B0/B1 no llaman a ningún LLM:
  - `ANTHROPIC_API_KEY` (si `RELATIONS_LLM_PROVIDER=anthropic`)
  - `OPENAI_API_KEY`    (si `RELATIONS_LLM_PROVIDER=openai`)
  - `GROQ_API_KEY`      (si `RELATIONS_LLM_PROVIDER=groq`)
  - `GEMINI_API_KEY`    (si `RELATIONS_LLM_PROVIDER=gemini`)
- `TIMELINE_LLM_MODEL` — sobreescribe el modelo de generación (defaults por proveedor: `Codex-haiku-4-5`, `gpt-4o-mini`, `llama-3.3-70b-versatile`, `gemini-flash-latest`).
- `RELATIONS_LLM_MODEL` — sobreescribe el modelo de clasificación de relaciones.
- `TIMELINE_API` — Streamlit frontend target (default `http://127.0.0.1:8000`).
- `NER_MODEL` — `spacy` (default) | `transformer`. NER backend for entity discovery (`src/pipeline/ner.py`).
- `SPACY_NER_MODEL` / `SPACY_DEP_MODEL` — spaCy models for NER and dep-parsing (default `es_core_news_lg`; `precompute_tema.py` falls back to `es_core_news_md` if unset, since that's the dev model that ships).
- `WIKIDATA_ENRIQUECER` — `1` (default) | `0`. Set `0` to skip Wikidata lookups in entity discovery (offline runs).
- `WIKIDATA_WORKERS` — parallel threads for Wikidata lookups (default 5).
- `TIMELINE_DATA_DIR` — root data dir (default `data`); also where `wikidata_cache.json` and `graph_<slug>.duckdb` live.

## Architecture

### The "swap point" invariant

The backbone is **fixed and shared** by all four conditions. Any divergence upstream of `generate()` contaminates the comparison. The pipeline:

```
ingest (andina / gdelt)
  → preprocess (dedup, clean)
    → NER + entity linking (src/pipeline/entities.py)
      → protagonism filter (src/pipeline/protagonism.py)
        → semantic clustering (src/pipeline/cluster.py — sentence-transformers + agglomerative)
          → saliency selection (src/pipeline/salience.py — ≥2 of 5 signals)
            ── SWAP POINT ──
            → generation condition (one of four)
              → assemble (src/assemble.py — sort by date)
```

All four conditions implement `GenerationCondition` (Protocol in `src/generation/base.py`): same input `list[EventCluster]`, same output `list[TimelineEntry]`.

### Four generation conditions (`src/generation/`)

| Name | File | LLM | Description |
|---|---|---|---|
| `b0_lead` | `b0_lead.py` | No | Copies the lead sentence of the representative document (quality floor) |
| `b1_extractive` | `b1_extractive.py` | No | Extractive: best sentence from evidence passages |
| `sistema_rag` | `sistema_rag.py` | Yes | RAG-grounded: LLM summarizes anchored to `pasajes_evidencia`; discards `SIN_RESPALDO` entries |
| `ablacion` | `ablacion.py` | Yes | Ablation: LLM without RAG anchoring, for contrast |

### Core data schemas (`src/schemas.py`)

These are the data contract — almost immutable. Changes affect all four conditions equally.

- `Documento` — ingested news article (`doc_id`, `fuente`, `url`, `fecha_pub`, `texto`, `entidades`)
- `EventCluster` — candidate event grouped by coreference (`cluster_id`, `fecha_normalizada`, `pasajes_evidencia`, `fuentes`, `fechas_evidencia`)
- `TimelineEntry` — generated timeline entry (`fecha`, `resumen`, `fuentes`, `confianza`, `cluster_id`)

**Attribution invariant (§2.6):** `TimelineEntry.fuentes` must never be empty. `SistemaRAG` discards entries the LLM cannot ground ("SIN_RESPALDO").

### Data layout (all under `data/`, gitignored)

```
data/
  figuras.json                  # manifest of precomputed figures/topics
  figuras_dinamicas.json        # figures created via the web UI
  corpus_<slug>.parquet         # ingested + annotated corpus per figure/topic
  graph_<slug>.duckdb           # knowledge graph per figure/topic (entities + relations)
  andina_crawl.jsonl            # full-archive crawl output (scripts/crawl_andina.py)
  andina_crawl.ckpt.json        # crawl checkpoint (resume point: ultimo_id, ok, vistos)
  wikidata_cache.json           # cached Wikidata lookups
  salidas/<slug>/
    b0_lead.json
    b1_extractive.json
    sistema_rag.json
    ablacion.json
  jobs/<slug>.json              # background job state (running/done/error)
  jobs/<slug>.log               # job stdout
```
Gold annotations live under `annotation/` (not `data/`): `gold_relaciones/`,
`gold_entidades/`, plus the `GUIA_ANOTACION.md` conventions. Reports/roadmap in `reports/`.

### Adding a new figure

1. Add a `FiguraConfig` entry to `FIGURAS` in `src/figuras.py`. Include:
   - `gazetteer`: surface form (lowercased, no accents) → `(canonical_id, name)` for the subject **and** all homonyms.
   - `sujeto_id`: canonical id of the subject.
   - `familia_otros`: homonym ids to **exclude** from protagonism (anti-contamination).
   - `queries`: search terms for Andina (single terms, not phrases — Andina searches by phrase internally).
   - `desde` / `hasta`: temporal window.
2. Run `python scripts/precompute_figura.py <slug>`.

Figures created via the web UI are stored in `data/figuras_dinamicas.json` and do not appear in `src/figuras.py`.

### Topic-centric pipeline (entity-relation graph)

Parallel to the four-conditions figure pipeline. Same ingest/preprocess, but
**no single subject**: no gazetteer, no protagonism filter. The product is a
knowledge graph, not a timeline.

```
ingest (topic queries) → preprocess (dedup, incl. cross-source)
  → entity discovery (pipeline/entity_discovery.py — NER over the WHOLE corpus,
       token-containment grouping, ACTOR filter (PER+ORG, generic denylist,
       applied BEFORE the top-N cut), Wikidata linking → top-N EntityNode)
    → co-occurrence extraction (pipeline/relations.py — sentences where ≥2
         entities appear; shallow dep-triple subject-verb-object)
      → relation classification (pipeline/relation_classifier.py —
           CalibratedClassifier: rules decide 'mencion', LLM decides every typed
           relation; per entity-pair; 'mencion' edges dropped)
        → knowledge graph (storage/graph.py — DuckDB persistence + NetworkX
             analytics) → manifest entry (tipo="tema")
```

Orchestrator: `scripts/precompute_tema.py <slug>`. It reuses
`data/corpus_<slug>.parquet` if present (so you can build a topic graph over an
existing figure's corpus by passing its slug), else scrapes from the topic's
`queries`. Output: `data/graph_<slug>.duckdb` + manifest registration.

**Multi-source ingestion.** `TemaConfig.fuentes` lists the collectors to use
(`"andina"`, `"gdelt"`; default `("andina",)`). `precompute_tema._colectar`
dispatches to each, merges, and `preprocess.preprocess` deduplicates **across
sources** by text signature; semantic clustering then merges paraphrased
republications of the same event. GDELT (`src/ingest/gdelt.py`) is the secondary
source — independent media, title-only `texto`, rate-limited (1 req / ≥5 s, so
`_colectar_gdelt` paces and tolerates per-query failures). Source provenance is
carried in the namespaced `doc_id` (`andina:…`, `gdelt:…`), which drives the
`multi_fuente` saliency signal (≥2 source families corroborating an event).

**Entity resolution (actor-focused).** `descubrir_entidades` defaults to keeping
only ACTORS (`_TIPOS_ACTOR` = PER+ORG) and dropping generic terms (`_GENERICOS`,
e.g. "Estado", "Gobierno"), filtering BEFORE the `top_n` cut so `top_n=20` yields
20 actors. This removed the LOC/MISC noise that dominated the first graphs
("Lima", "Cusco", "Estado", "Ley"). Override with `tipos=`/`excluir=` to keep
locations. Residual acronym noise (e.g. "NDP", "FHG") is left for the human gold
to flag, not hard-filtered. Quality is measured by `eval/entities.py`.

**Config:** `TemaConfig` / `TEMAS` in `src/figuras.py` (no `sujeto_id`,
`gazetteer`, or `familia_otros` — just `queries`, window, `top_n`, `pais`).
`figuras.cargar_tema(slug)` adapts an existing `FiguraConfig` to a `TemaConfig`
when the slug is a figure, enabling corpus reuse.

**Relation taxonomy** (`src/schemas.py` `TIPOS_RELACION`, single source of
truth): `alianza`, `conflicto`, `pertenencia`, `nombramiento`, `acusacion`,
`ruptura`, `mencion`. Four classifiers implement the `RelationClassifier`
Protocol: `RuleBasedClassifier` (verb lexicon, no LLM), `LLMClassifier`
(provider-agnostic), `HybridClassifier` (escalates to LLM below a confidence
threshold), and **`CalibratedClassifier`** — the one `precompute_tema` uses.

`CalibratedClassifier` routes by PREDICTED TYPE, not by confidence: rules decide
`mencion` only (measured precision 0.90–1.00); every TYPED rule prediction goes
to the LLM to confirm/correct. This is the gold-justified fix
(reports/resultados-relaciones.md): the old umbral-based hybrid was useless
(accuracy ≈0.27 ≈ rules) because rule ERRORS are high-confidence, so the 0.65
threshold never verified them; the LLM scored 0.75. All classifiers degrade to
rules if the LLM hits a quota error or no API key. The relations LLM runs at
`temperature=0.0` (Anthropic has no seed; `Codex-haiku-4-5`).

`precompute_tema` drops `mencion` edges entirely (a co-occurrence without a typed
relation is not a graph edge) and classifies per UNIQUE entity-pair via
`classify_grupo` (~O(pairs), not O(sentences)). `preprocess.limpiar` strips
Andina credit lines / bylines ("(FIN) NDP/JCR Publicado: dd/mm/aaaa") so reporter
initials (NDP/FHG/HTC) don't enter the graph as spurious ORG entities.

**Graph schemas** (`src/schemas.py`): `EntityNode` (graph node; `entity_id` is a
Wikidata QID when linked, else a slug), `RelationResult` (classifier output),
`RelationEdge` (graph edge with `evidencia`, `fuentes`, `confianza`, `metodo`,
plus `predicado` = the OPEN relation verb and `tipo` now **nullable** = the
category, assigned later or left None). `metodo` ∈ {rules, llm, hybrid, human,
openie} preserves provenance for auditing/curation. An edge can be **typed**
(`tipo` set, `predicado` None — the classifier route) or **open** (`predicado`
set, `tipo` None — the OpenIE/temporal route, typed later).

**Storage** (`src/storage/graph.py`): one `KnowledgeGraph` per slug, file
`data/graph_<slug>.duckdb`. DuckDB for SQL queries (filter relations by date /
type / confidence / entity); NetworkX for `centralidad` (PageRank),
`comunidades` (Louvain), `camino` (shortest path). Open `read_only=True` in the
API. Exposed read-only at `/api/figuras/{slug}/grafo/{entidades,relaciones,
centralidad,comunidades,camino}` and `/grafo/relaciones/{rel_id}/evidencia`
(passages + sources resolved to {doc_id,url,titulo}; relations don't carry
evidence inline, fetched on demand per edge).

The manifest (`data/figuras.json`) now tags each entry with `tipo`:
`"figura"` (4-condition timeline) or `"tema"` (graph; carries `n_entidades`,
`n_relaciones`, `rango_fechas` instead of `n_eventos`).

### Open-temporal relations (OpenIE, type later) + full Andina crawl

Parallel regime to the typed topic graph, for the full-archive direction.

**Full crawl** (`scripts/crawl_andina.py`): Andina's *search* is capped (~300
results/query, ~2021). To get **everything, all topics, incl. pre-2021 history**,
enumerate article IDs — `andina.pe/agencia/noticia-x-<id>.aspx` accepts any slug
and redirects to the real note. Resumable (checkpoint `data/andina_crawl.ckpt.json`),
date-filtered, writes `data/andina_crawl.jsonl` (same 5-field schema as the corpus
parquet). Measured: ~96% of IDs are notes, ~2 ids/s, ~130 notes/calendar-day; id
1.0M ≈ 2024-09; **2021-2026 ≈ ids 828k–1.085M (~38 h)**. ⚠ English notes are mixed
in (Andina's English service) — filter by language.

**Open relations (OpenIE-lite).** `relations.relacion_abierta(oracion, a, b, nlp)`
/ `relations.extraer_relaciones_abiertas(docs, entidades)` return the **free
connecting verb** between two entities via the dependency path (surface form —
`_nlp_dep` disables the lemmatizer). No taxonomy at extraction; the **type is
induced later** (predicate clustering, WS3 in `reports/roadmap-paper.md`).

**Temporal multigraph.** `scripts/build_open_graph.py` consumes a corpus
(`--jsonl` crawl or `corpus_<slug>.parquet` via `--corpus-slug`), applies a
language filter (`es_espanol`), discovers entities, then inserts **one dated open
edge per co-occurrence** (deduped by pair+date+predicate) — it does **not**
collapse per pair. So the same pair has many dated edges and
`graph.evolucion(a, b)` (bidirectional, date-sorted) reconstructs how the
relationship **evolves over time**. Validated on the roberto-sanchez corpus:
40 entities, 5573 dated open edges.

### Web app and background jobs (`src/app/`)

The FastAPI backend (`api.py`) is **read-only at request time** — it never runs the pipeline or calls the LLM during a web request. All heavy work happens offline via `scripts/precompute_figura.py`.

When a new figure is created from the web (POST `/api/figuras`), `jobs.py` launches `precompute_figura` as a **detached subprocess** (`python -m src.app.jobs <slug>`). The web polls `GET /api/jobs/{slug}` for state. `jobs.py` is intentionally lightweight (no spaCy/torch imports at module level).

The static web frontend lives in `src/app/web/` and is mounted at `/` after all `/api/*` routes.

Two views, switched by the topbar toggle (`grafo.js`, independent of `app.js`
via `window.__vistaGrafo`): **Cronología** (the timeline, `app.js`) and **Grafo**
(the topic-centric relation network, `grafo.js`). The graph view uses cytoscape
(CDN), colours nodes by type (PER/ORG) and edges by relation type, filters by
relation type / min-confidence / date range, shows per-edge evidence + sources on
edge click, and a node's relations in chronological order (the derived
figure-timeline view) on node click. A figure without a graph shows a "run
precompute_tema" message.

### Saliency signals (`src/pipeline/salience.py`)

A cluster is salient if ≥2 of 5 signals are true:
1. **prominencia** — subject appears in ≥1 evidence passage title
2. **nota_dedicada** — ≥2 source documents
3. **cobertura_sostenida** — ≥2 distinct publication dates
4. **consecuencia** — lexical proxy for judicial outcomes (sentencia, prisión, …)
5. **multi_fuente** — cluster has doc_ids from ≥2 source families (e.g. andina + gdelt), derived from the `doc_id` prefix. Inert for mono-source (Andina-only) corpora; active once GDELT/other sources are ingested.

### LLM client (`src/generation/_llm.py`)

Shared by SistemaRAG and Ablación. Delegates to `src/llm/_config.py` — the provider is resolved from `RELATIONS_LLM_PROVIDER` at startup (anthropic / openai / groq / gemini). Default model per provider configured in `_DEFAULTS`. Temperature fixed at 0.7 per §5. Call count and USD cost accumulated per-process via `_llm.costo()`. Run-to-run variation is inherent (no seed parameter across providers).

### Evaluation (`eval/`)

- `align.py` — 1-to-1 greedy alignment of predicted vs gold `TimelineEntry` by date (±tolerance) then ROUGE-1 similarity
- `metrics.py` — Date F1, ROUGE (aligned), hallucination rate (injecting a `verificador(resumen, premisa) -> bool`)
- `nli.py` — default NLI/entailment judge in Spanish (torch-backed; lazy import)
- `run_experiment.py` — 4 conditions × N≥3 runs, aggregates mean ± stdev; requires gold CSV in `annotation/gold/`
- `entities.py` — **entity-resolution evaluation**: actor precision (noise that survives the filter), actor recall (real actors wrongly dropped), type accuracy, and split detection (one actor spread across nodes). Gold CSV in `annotation/gold_entidades/<slug>.csv`; generate it with `scripts/export_entidades_gold.py` (exports the RAW discovered set marking which survive the actor filter), validate with `scripts/test_entities.py`.
- `relations.py` — **relation-classifier evaluation (topic-centric headline metric)**. Per-type precision/recall/F1, accuracy, macro-F1, confusion matrix; `comparar(..., con_llm=True)` runs rules vs hybrid vs LLM on the same examples to pick the hybrid threshold. Gold CSV in `annotation/gold_relaciones/<slug>.csv` (columns: `entity_a, entity_b, oracion, doc_id, fecha, triple_*, tipo_sugerido, tipo_gold`; rows with empty `tipo_gold` are skipped). Generate the unlabeled CSV with `scripts/export_relaciones_gold.py` (stratified by suggested type), validate the harness with `scripts/test_relations.py` before the gold arrives.

In the topic-centric pivot, **relation classification quality replaces the
hallucination rate as the headline metric** (the 4-condition generation is now an
optional narrative layer). Known rule-lexicon gap surfaced by the harness: the
`militan` pattern misses the verb conjugation "milita" (militar→milita); tune the
lexicon (`relation_classifier.py` `_LEXICON`) against real gold, not blindly.

Gold format: CSV with columns `fecha`, `descripcion`, `fuentes` (comma-separated doc_ids). Gold is frozen before the experiment runs.

The hallucination rate (tasa de alucinación) is the headline metric. The NLI judge must be validated against a human-labeled subset before reporting (see `eval.nli.validar_juez`).

Validate the metric harness **before** the gold arrives: `python scripts/test_eval.py`.

Compact guidance for OpenCode sessions in this repo. For full background, read `CLAUDE.md`; keep this file to the repo-specific things agents are likely to miss.

## Setup And Commands

- Python package is `timeline-gen` and requires Python `>=3.12,<3.14`; local development is pinned to Python `3.13` in `.python-version` because current spaCy wheels do not support Python 3.14.
- Install dependencies from the repo root with `uv sync`; run project commands with `uv run`.
- Install spaCy Spanish model `es_core_news_md` for dev/smoke work with `uv run python -m spacy download es_core_news_md`; use `es_core_news_lg` for production precompute if available.
- Copy `.env.example` to `.env` locally. `RELATIONS_LLM_PROVIDER` controls both relation classification and timeline generation; only the active provider key is needed.
- Run the backend/static frontend with `uv run uvicorn src.app.api:app --reload` and open `http://127.0.0.1:8000`.
- Useful focused checks are plain scripts, not a configured pytest suite: `uv run python -m compileall -q src scripts eval`, `uv run python scripts/test_relations.py`, `uv run python scripts/test_entities.py`, `uv run python scripts/test_multifuente.py`, `uv run python scripts/test_eval.py`.
- `uv run python -m eval.run_experiment 3` requires frozen gold under `annotation/gold/`; relation/entity evals require their CSVs under `annotation/gold_relaciones/` and `annotation/gold_entidades/`.

## Offline Pipeline Boundary

- `src/app/api.py` is read-only at request time: do not scrape, run spaCy/torch-heavy pipeline code, or call LLMs from web requests.
- Figure precompute is offline via `uv run python scripts/precompute_figura.py <slug>` and writes `data/corpus_<slug>.parquet`, `data/salidas/<slug>/*.json`, `data/graph_<slug>.duckdb`, and `data/figuras.json`.
- Topic graph precompute is offline via `uv run python scripts/precompute_tema.py <slug>`; it reuses `data/corpus_<slug>.parquet` if present, otherwise scrapes configured topic sources.
- Open-temporal graph build is `uv run python scripts/build_open_graph.py <slug> --jsonl data/andina_crawl.jsonl --top-n 300` or `--corpus-slug <other>`; it creates one dated open edge per co-occurrence and leaves `tipo=None` for later typing.
- Precompute/build scripts delete an existing `data/graph_<slug>.duckdb` for a clean rerun; do not run them casually when preserving a local graph matters.

## Architecture Invariants

- The four timeline conditions must share the same backbone output up to the swap point: ingest/preprocess/entities/protagonism/cluster/salience all happen before `GenerationCondition.generate()`.
- All generation conditions return `list[TimelineEntry]`; keep `TimelineEntry.fuentes` non-empty for attribution.
- `src/schemas.py` is the shared data contract and relation taxonomy source of truth; do not redefine `TIPOS_RELACION` elsewhere.
- Figure configs live in `src/figuras.py`; include homonyms in `gazetteer` and exclude them through `familia_otros`, otherwise timelines get contaminated.
- Andina search behaves like phrase search; existing figure/topic configs intentionally use specific search terms instead of assuming broad keyword semantics.
- Topic graphs have no single subject and no protagonism filter. `precompute_tema` keeps PER/ORG actors, drops generic entities before `top_n`, groups co-occurrences by entity pair, and drops `mencion` edges entirely.
- With an LLM key, `precompute_tema` uses `CalibratedClassifier`: rules decide `mencion`, typed rule predictions are confirmed/corrected by the LLM. Without a key it falls back to rules.
- The open-relation path in `scripts/build_open_graph.py` is OpenIE-lite, no LLM, Spanish-language filtered, and must not collapse multiple dated edges for the same pair.

## Data And Generated Files

- `data/figuras.json` and `data/salidas/` are intended outputs in git; `data/*.parquet`, `data/*.duckdb`, `data/*.csv`, `data/*.xlsx`, `data/jobs/`, `data/wikidata_cache.json`, and `.env` are local/generated.
- Gold annotations live under `annotation/`, not `data/`; local `.xlsx/.csv/.parquet` gold workbooks under `annotation/gold/` are ignored.
- `TIMELINE_DATA_DIR` changes the data root for `KnowledgeGraph` DuckDB files and API graph checks. Set it before importing `src.storage`/`KnowledgeGraph` in tests or scripts that need an isolated temp DB.

## App Structure

- FastAPI routes are in `src/app/api.py`; static frontend files are in `src/app/web/` and are mounted after `/api/*` routes.
- The web UI has separate timeline and graph JS (`app.js` and `grafo.js`); keep the graph view independent via `window.__vistaGrafo`.
- Background jobs are launched through `src/app/jobs.py` as detached precompute subprocesses; keep that module lightweight at import time.
