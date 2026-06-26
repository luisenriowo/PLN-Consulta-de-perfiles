# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`timeline-gen` is a NLP research pipeline (T02 — Generación de lenguaje) that builds political-figure timelines from a Spanish news corpus (Agencia Andina primary, GDELT secondary). It compares four generation conditions — B0Lead, B1Extractive, SistemaRAG, Ablación — on the **same** backbone-produced event clusters, then serves the results via a FastAPI + static-web backend.

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

# Build Humala corpus from scratch (scraping + NER + gate-metrics)
python scripts/build_corpus.py

# Run generation only (reads existing corpus_humala.parquet)
python scripts/run_generation.py

# Evaluate: 4 conditions × N runs (requires gold in annotation/gold/)
python -m eval.run_experiment [N]

# Validate eval harness with known-answer fixtures (no gold needed)
python scripts/test_eval.py

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
- `TIMELINE_LLM_MODEL` — sobreescribe el modelo de generación (defaults por proveedor: `claude-haiku-4-5`, `gpt-4o-mini`, `llama-3.3-70b-versatile`, `gemini-flash-latest`).
- `RELATIONS_LLM_MODEL` — sobreescribe el modelo de clasificación de relaciones.
- `TIMELINE_API` — Streamlit frontend target (default `http://127.0.0.1:8000`).

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
  figuras.json                  # manifest of precomputed figures
  figuras_dinamicas.json        # figures created via the web UI
  corpus_<slug>.parquet         # ingested + annotated corpus per figure
  salidas/<slug>/
    b0_lead.json
    b1_extractive.json
    sistema_rag.json
    ablacion.json
  jobs/<slug>.json              # background job state (running/done/error)
  jobs/<slug>.log               # job stdout
```

### Adding a new figure

1. Add a `FiguraConfig` entry to `FIGURAS` in `src/figuras.py`. Include:
   - `gazetteer`: surface form (lowercased, no accents) → `(canonical_id, name)` for the subject **and** all homonyms.
   - `sujeto_id`: canonical id of the subject.
   - `familia_otros`: homonym ids to **exclude** from protagonism (anti-contamination).
   - `queries`: search terms for Andina (single terms, not phrases — Andina searches by phrase internally).
   - `desde` / `hasta`: temporal window.
2. Run `python scripts/precompute_figura.py <slug>`.

Figures created via the web UI are stored in `data/figuras_dinamicas.json` and do not appear in `src/figuras.py`.

### Web app and background jobs (`src/app/`)

The FastAPI backend (`api.py`) is **read-only at request time** — it never runs the pipeline or calls the LLM during a web request. All heavy work happens offline via `scripts/precompute_figura.py`.

When a new figure is created from the web (POST `/api/figuras`), `jobs.py` launches `precompute_figura` as a **detached subprocess** (`python -m src.app.jobs <slug>`). The web polls `GET /api/jobs/{slug}` for state. `jobs.py` is intentionally lightweight (no spaCy/torch imports at module level).

The static web frontend lives in `src/app/web/` and is mounted at `/` after all `/api/*` routes.

### Saliency signals (`src/pipeline/salience.py`)

A cluster is salient if ≥2 of 5 signals are true:
1. **prominencia** — subject appears in ≥1 evidence passage title
2. **nota_dedicada** — ≥2 source documents
3. **cobertura_sostenida** — ≥2 distinct publication dates
4. **consecuencia** — lexical proxy for judicial outcomes (sentencia, prisión, …)
5. **multi_fuente** — currently inert (corpus is mono-source: Andina)

### LLM client (`src/generation/_llm.py`)

Shared by SistemaRAG and Ablación. Delegates to `src/llm/_config.py` — the provider is resolved from `RELATIONS_LLM_PROVIDER` at startup (anthropic / openai / groq / gemini). Default model per provider configured in `_DEFAULTS`. Temperature fixed at 0.7 per §5. Call count and USD cost accumulated per-process via `_llm.costo()`. Run-to-run variation is inherent (no seed parameter across providers).

### Evaluation (`eval/`)

- `align.py` — 1-to-1 greedy alignment of predicted vs gold `TimelineEntry` by date (±tolerance) then ROUGE-1 similarity
- `metrics.py` — Date F1, ROUGE (aligned), hallucination rate (injecting a `verificador(resumen, premisa) -> bool`)
- `nli.py` — default NLI/entailment judge in Spanish (torch-backed; lazy import)
- `run_experiment.py` — 4 conditions × N≥3 runs, aggregates mean ± stdev; requires gold CSV in `annotation/gold/`

Gold format: CSV with columns `fecha`, `descripcion`, `fuentes` (comma-separated doc_ids). Gold is frozen before the experiment runs.

The hallucination rate (tasa de alucinación) is the headline metric. The NLI judge must be validated against a human-labeled subset before reporting (see `eval.nli.validar_juez`).

Validate the metric harness **before** the gold arrives: `python scripts/test_eval.py`.
