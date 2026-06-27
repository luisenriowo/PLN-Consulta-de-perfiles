# PLN — Consulta de Perfiles

Pipeline NLP (T02 — Generación de lenguaje) que construye cronologías de figuras políticas a partir del corpus de noticias de Agencia Andina. Compara cuatro condiciones de generación (B0Lead, B1Extractive, SistemaRAG, Ablación) sobre los mismos clusters de eventos, y sirve los resultados vía una API FastAPI + frontend web estático.

---

## Configuración inicial

### 1. Entrar al proyecto y crear entorno virtual

```powershell
cd PLN-Consulta-de-perfiles
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

El prompt debe mostrar `(.venv)`.

### 2. Instalar dependencias

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
python -m spacy download es_core_news_md
```

### 3. Configurar variables de entorno

```powershell
copy .env.example .env
```

Edita `.env` y completa la API key del proveedor LLM que el equipo usa (solo necesaria para SistemaRAG y Ablación; B0/B1 no hacen ninguna llamada LLM). Ver `.env.example` para opciones de proveedor.

### 4. Obtener los datos

Las salidas ya generadas están en el repositorio (`data/salidas/`). No hace falta reprocesar nada para ver la aplicación.

Si en algún momento necesitas regenerar una figura desde cero:

```powershell
python scripts/precompute_figura.py humala
```

### 5. Levantar el backend

```powershell
uvicorn src.app.api:app --reload
```

Abre `http://127.0.0.1:8000` — muestra el frontend con las cronologías ya cargadas.

---

## Estructura de datos

```
data/
  figuras.json              # manifiesto de figuras disponibles (en git)
  salidas/<slug>/           # salidas generadas por condición (en git)
    b0_lead.json
    b1_extractive.json
    sistema_rag.json
    ablacion.json
  corpus_<slug>.parquet     # corpus crudo (gitignoreado — regenerable)
  graph_<slug>.duckdb       # grafo de relaciones (gitignoreado — regenerable)
```

---

## Comandos útiles

```powershell
# Verificar entorno
python -c "import pandas, spacy; spacy.load('es_core_news_md'); print('OK')"

# Validar sintaxis del proyecto
python -m compileall -q src scripts eval

# Evaluar condiciones (requiere gold en annotation/gold/)
python -m eval.run_experiment 3

# Smoke test ingest (sin scraping completo)
python scripts/smoke_ingest.py

# Frontend legacy Streamlit (requiere backend activo)
streamlit run src/app/streamlit_app.py
```

---

## Notas

- Las condiciones B0 y B1 no requieren API key de ningún proveedor LLM.
- Cambiar de proveedor LLM es solo cambiar `RELATIONS_LLM_PROVIDER` en `.env` — cero cambios de código.
- Para investigación: todos los experimentos de evaluación deben usar el mismo proveedor y modelo para que la comparación sea válida.
