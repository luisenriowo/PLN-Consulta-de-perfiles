# PLN Consulta de Perfiles

## Configuracion inicial

### 1. Entrar a la raiz del proyecto

```powershell
cd PLN-Consulta-de-perfiles
```

### 2. Crear entorno virtual

```powershell
python -m venv .venv
```

### 3. Activar entorno virtual

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activacion:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

El prompt debe mostrar:

```text
(.venv) PS ...\PLN-Consulta-de-perfiles>
```

### 4. Actualizar pip

```powershell
python -m pip install --upgrade pip
```

### 5. Instalar dependencias del proyecto

```powershell
python -m pip install -e .
```

### 6. Instalar modelo spaCy requerido

```powershell
python -m spacy download es_core_news_md
```

### 7. Verificar instalacion

```powershell
python -c "import pandas, pyarrow, bs4, lxml, requests, spacy, sentence_transformers, sklearn, fastapi, streamlit, rouge_score, anthropic; spacy.load('es_core_news_md'); print('OK')"
```

### 8. Generar corpus

```powershell
python scripts/build_corpus.py
```

Genera:

```text
data/corpus_humala.parquet
data/corpus_metrics.json
```

### 9. Generar eventos

```powershell
python scripts/build_events.py
```

Genera:

```text
data/eventos_humala.parquet
```

### 10. Generar salidas B0/B1

```powershell
python scripts/run_generation.py
```

Genera:

```text
data/salidas/b0_lead.json
data/salidas/b1_extractive.json
```

### 11. Exportar spreadsheet para anotadores

```powershell
python scripts/export_corpus_spreadsheet.py
```

Genera:

```text
data/corpus_humala_anotacion.xlsx
data/corpus_humala_anotacion.csv
```

## Comandos utiles

### Verificar Python activo

```powershell
where python
python -c "import sys; print(sys.executable)"
python -m pip -V
```

Debe apuntar a:

```text
...\PLN-Consulta-de-perfiles\.venv\Scripts\python.exe
```

### Validar sintaxis del proyecto

```powershell
python -m compileall -q src scripts eval
```

## Notas

- `data/` esta ignorado por git.
- Los archivos `.parquet` y `.json` generados no se suben al repositorio.
- `es_core_news_lg` es opcional por ahora.
- `scripts/build_corpus.py` requiere internet.
