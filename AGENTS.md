# AGENTS.md

Compact guidance for OpenCode sessions in this repo. For long-form architecture notes, read `CLAUDE.md`; keep this file to details future agents are likely to miss.

## Setup And Commands

- Python package is `timeline-gen`; `pyproject.toml` requires Python `>=3.12,<3.14`, and local dev is pinned to `3.13` in `.python-version`.
- Use `uv sync` from the repo root; run project commands with `uv run`, not bare `python`/`pip`.
- Install the dev Spanish spaCy model with `uv run python -m spacy download es_core_news_md`; use `es_core_news_lg` only for production precompute if available.
- Run the FastAPI/static frontend with `uv run uvicorn src.app.api:app --reload` and open `http://127.0.0.1:8000`.
- Run the legacy Streamlit frontend with `uv run streamlit run src/app/streamlit_app.py`; it expects the backend to be running.
- There is no configured pytest suite, CI workflow, pre-commit hook, Makefile, or task runner in the repo. Focused checks are standalone scripts.
- Useful checks: `uv run python -m compileall -q src scripts eval`, `uv run python scripts/test_relations.py`, `uv run python scripts/test_entities.py`, `uv run python scripts/test_multifuente.py`, `uv run python scripts/test_eval.py`, `uv run python scripts/test_grafo_api.py`, `uv run python scripts/test_relation_typing.py`.
- `uv run python -m eval.run_experiment 3` requires frozen timeline gold under `annotation/gold/`; relation/entity evals require CSV gold under `annotation/gold_relaciones/` and `annotation/gold_entidades/`.

## Environment

- Copy `.env.example` to `.env` locally. Only the active provider key is required.
- `RELATIONS_LLM_PROVIDER` controls both relation classification and timeline generation. Without `.env`, code defaults to `anthropic`; `.env.example` currently sets `gemini`.
- `RELATIONS_LLM_MODEL` / `TIMELINE_LLM_MODEL` override provider defaults; relation temperature defaults to `0.0`, timeline generation to `0.7`.
- `SPACY_NER_MODEL` and `SPACY_DEP_MODEL` default to the medium model in local scripts when set from `.env.example`.
- `TIMELINE_DATA_DIR` is read at import time by graph storage/API graph checks. Set it before importing `src.storage`, `KnowledgeGraph`, or `src.app.api` in tests that need an isolated graph DB.

## Offline Pipeline Boundary

- `src/app/api.py` is read-only at request time: do not scrape, run spaCy/torch-heavy pipeline code, or call LLMs from web requests.
- Figure precompute is offline: `uv run python scripts/precompute_figura.py <slug>`. It reuses `data/corpus_<slug>.parquet` if present, writes `data/salidas/<slug>/*.json`, `data/graph_<slug>.duckdb`, and updates `data/figuras.json`.
- Without an LLM key, `precompute_figura.py` writes only B0/B1 timeline outputs and skips `SistemaRAG`/`Ablacion`.
- Topic graph precompute is offline: `uv run python scripts/precompute_tema.py <slug>`. It reuses `data/corpus_<slug>.parquet` if present; otherwise it scrapes configured topic sources.
- `precompute_tema.py` and `build_open_graph.py` delete any existing `data/graph_<slug>.duckdb` for a clean rerun. Do not run them casually when a local graph must be preserved.
- Full Andina crawling by ID is resumable but expensive: `uv run python scripts/crawl_andina.py --desde-id ... --hasta-id ... --salida data/andina_crawl.jsonl --delay 0.5`.
- Open-temporal graph build is `uv run python scripts/build_open_graph.py <slug> --jsonl data/andina_crawl.jsonl --top-n 300` or `--corpus-slug <other>`; add `--inicio MM-YYYY --fin MM-YYYY` for an inclusive monthly date range, and `--menciones` to reuse persisted NER mentions for parquet inputs.

## Architecture Invariants

- The four timeline conditions must share the same backbone output up to the swap point: ingest/preprocess/entities/protagonism/cluster/salience happen before `GenerationCondition.generate()`.
- All generation conditions return `list[TimelineEntry]`; keep `TimelineEntry.fuentes` non-empty for attribution.
- `src/schemas.py` is the shared data contract and the single source of truth for `TIPOS_RELACION`; do not redefine the relation taxonomy elsewhere.
- Ingested `Documento.doc_id` must be namespaced by source, e.g. `andina:123` or `gdelt:https://...`; salience derives the `multi_fuente` signal from this prefix.
- `preprocess.preprocess` deduplicates cross-source by text signature. Do not remove the byline/credit stripping that keeps reporter initials like `NDP` out of entity discovery.
- Figure configs live in `src/figuras.py`. Include homonyms in `gazetteer` and exclude them through `familia_otros`; do not link ambiguous surnames alone unless the config already proves it is safe.
- Andina search behaves like phrase search. Existing figure/topic configs intentionally use specific search terms instead of broad keyword assumptions.
- Topic graphs have no single subject and no protagonism filter. `precompute_tema.py` keeps PER/ORG actors, drops generic entities before `top_n`, classifies per unique entity pair, and drops `mencion` edges entirely.
- With an LLM key, `precompute_tema.py` uses `CalibratedClassifier`: rules decide only `mencion`, and typed rule predictions are confirmed/corrected by the LLM. Without a key it falls back to rules.
- Open-relation graphs are OpenIE-lite and no-LLM: Spanish-language filtered, `predicado` set, `tipo=None` until later typing, and one dated edge per co-occurrence rather than one collapsed edge per pair.

## Data And Generated Files

- `data/figuras.json` and `data/salidas/` are intended outputs in git.
- `data/*.parquet`, `data/*.duckdb`, `data/*.csv`, `data/*.xlsx`, `data/*.jsonl`, `data/*.ckpt.json`, `data/jobs/`, `data/wikidata_cache.json`, `data/figuras_dinamicas.json`, and `.env` are local/generated.
- Gold annotations live under `annotation/`, not `data/`; local `.xlsx`, `.csv`, and `.parquet` workbooks under `annotation/gold/` are ignored.
- Figure/topic manifest entries use `tipo`: `figura` has four-condition timeline outputs, while `tema` has graph counts and no timeline condition JSONs.

## App Structure

- FastAPI routes are in `src/app/api.py`; static frontend files are in `src/app/web/` and are mounted after all `/api/*` routes.
- The web UI keeps timeline and graph code separate: `app.js` for Cronologia, `grafo.js` for Grafo, coordinated through `window.__vistaGrafo`.
- Background jobs are launched through `src/app/jobs.py` as detached subprocesses; keep that module lightweight at import time and avoid top-level spaCy/torch imports.
