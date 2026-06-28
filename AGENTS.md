# AGENTS.md

Compact guidance for OpenCode sessions in this repo. For full background, read `CLAUDE.md`; keep this file to the repo-specific things agents are likely to miss.

## Setup And Commands

- Python package is `timeline-gen` and requires Python `>=3.11`; install from the repo root with `pip install -e .`.
- Install spaCy Spanish model `es_core_news_md` for dev/smoke work; use `es_core_news_lg` for production precompute if available.
- Copy `.env.example` to `.env` locally. `RELATIONS_LLM_PROVIDER` controls both relation classification and timeline generation; only the active provider key is needed.
- Run the backend/static frontend with `uvicorn src.app.api:app --reload` and open `http://127.0.0.1:8000`.
- Useful focused checks are plain scripts, not a configured pytest suite: `python -m compileall -q src scripts eval`, `python scripts/test_relations.py`, `python scripts/test_entities.py`, `python scripts/test_multifuente.py`, `python scripts/test_eval.py`.
- `python -m eval.run_experiment 3` requires frozen gold under `annotation/gold/`; relation/entity evals require their CSVs under `annotation/gold_relaciones/` and `annotation/gold_entidades/`.

## Offline Pipeline Boundary

- `src/app/api.py` is read-only at request time: do not scrape, run spaCy/torch-heavy pipeline code, or call LLMs from web requests.
- Figure precompute is offline via `python scripts/precompute_figura.py <slug>` and writes `data/corpus_<slug>.parquet`, `data/salidas/<slug>/*.json`, `data/graph_<slug>.duckdb`, and `data/figuras.json`.
- Topic graph precompute is offline via `python scripts/precompute_tema.py <slug>`; it reuses `data/corpus_<slug>.parquet` if present, otherwise scrapes configured topic sources.
- Open-temporal graph build is `python scripts/build_open_graph.py <slug> --jsonl data/andina_crawl.jsonl --top-n 300` or `--corpus-slug <other>`; it creates one dated open edge per co-occurrence and leaves `tipo=None` for later typing.
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
