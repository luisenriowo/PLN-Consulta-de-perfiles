#!/bin/bash
set -e

echo "=== INICIANDO PIPELINE DE CLUSTERING (NER=spacy) ==="
date

echo ""
echo "1) CONSOLIDAR CORPUS"
# .venv/bin/python scripts/consolidar_corpus.py --jsonl data/andina_crawl.jsonl --version v2

echo ""
echo "2) NER (Extracción de Entidades con SpaCy)"
# NER_MODEL=spacy SPACY_NER_MODEL=es_core_news_md .venv/bin/python scripts/ner_corpus.py --corpus data/corpus_andina_v2.parquet

echo ""
echo "3) CONSTRUCCIÓN DE GRAFO ABIERTO (Top 150 actores)"
RELATIONS_NLP_PROCS=6 .venv/bin/python scripts/build_open_graph.py andina-v2 --corpus-slug andina_v2 --menciones --top-n 150 --limit 50000

echo ""
echo "4) CLUSTERING (Tipado Inducido)"
.venv/bin/python scripts/export_relation_type_clusters.py andina-v2

echo ""
echo "=== PIPELINE COMPLETADO EXITOSAMENTE ==="
date
