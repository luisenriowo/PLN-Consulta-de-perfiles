# Datasheet — Corpus Andina 2021-2026 (§Datos del paper)

*Estilo Gebru et al. (2021), "Datasheets for Datasets". Esqueleto pre-llenado;
los `TODO` requieren decisión/redacción humana. Las cifras se leen de
`data/corpus_andina_<version>.manifest.json` (no copiar a mano: citar el manifiesto).*

## Motivación
- **¿Para qué se creó?** Construir un grafo TEMPORAL de relaciones abiertas entre
  entidades a partir del archivo de noticias de la Agencia Andina, para estudiar
  cómo evolucionan las relaciones entre actores (personas, partidos, instituciones)
  en 2021-2026. Recurso para NLP en español y análisis político.
- **¿Quién lo creó / financió?** TODO (equipo, curso, institución).

## Composición
- **Instancias:** notas de prensa (título + lead + cuerpo) de andina.pe.
- **Nº de instancias:** ver `manifest.n_final_es` (v1 parcial: ~11.3k, casi todo
  2021 porque el crawl aún recorre esa franja de IDs; la versión final cubrirá
  2021-2026). Distribución por año/mes en `manifest.stats`.
- **Idioma:** español (las notas en inglés del servicio en inglés de Andina se
  descartan — ~6.8% en v1, ver `manifest.tasa_descarte_idioma`).
- **Campos por instancia:** `doc_id` (`andina:<id>`), `fuente` (`andina.pe`),
  `url`, `fecha_pub` (ISO, fecha de publicación = DCT), `texto` (título\nlead\ncuerpo).
- **¿Etiquetas?** No en el corpus base. El gold (entidades, relaciones, tipos) vive
  aparte en `annotation/`.
- **¿Datos faltantes?** Notas sin h1/fecha se descartan en el parseo. IDs no
  cronológicos → ordenar por `fecha_pub`, no por id.

## Proceso de recolección
- **¿Cómo se obtuvo?** Crawl por **enumeración de IDs** de URL
  (`andina.pe/agencia/noticia-x-<id>.aspx` acepta cualquier slug y redirige).
  Script: `scripts/crawl_andina.py`. La búsqueda del sitio está capada (~300/query,
  ~2021), por eso se enumeran IDs (alcanza también el histórico).
- **Ventana:** 2021-01-01 … 2026-12-31 (IDs ~825k–1.1M; calibración id↔fecha en
  `memory`/roadmap). ~96% de IDs son notas válidas; ~2 ids/s.
- **Cortesía / legalidad:** robots.txt de andina.pe = `Allow: /`; se verifica antes
  de cada fetch y se aplica rate limit (`--delay`). User-Agent identificado (uso
  académico).
- **Marca temporal del crawl:** ver `manifest.fecha_consolidacion` + rango de IDs.

## Preprocesamiento / limpieza
- Dedup por **firma de texto** (cross-fuente); descarte de notas < 60 chars;
  eliminación de **bylines** de redacción ("(FIN) NDP/JCR Publicado: fecha").
- **Filtro de idioma** (heurístico ES vs EN). Pipeline en `scripts/consolidar_corpus.py`.
- **Congelado y versionado:** parquet + `sha256` en el manifiesto (reproducibilidad).
- **TODO:** ¿se resuelven fechas relativas del texto (HeidelTime)? v1 usa solo
  `fecha_pub` (DCT) — declararlo como limitación.

## Usos
- **Previstos:** investigación NLP (NER, OpenIE, KG temporal), análisis político
  (evolución de relaciones), demo/explorador.
- **No recomendados / riesgos:** afirmar hechos sobre personas a partir de las
  relaciones extraídas (son aserciones *atribuidas a la fuente*, no verificadas);
  decisiones sobre individuos.

## Distribución / mantenimiento
- **TODO:** ¿se libera el corpus? ¿bajo qué licencia/condiciones? (derechos de
  Andina sobre el contenido — considerar liberar solo IDs+metadatos+anotaciones,
  no el texto completo, según términos).
- **Versionado:** `corpus_andina_v<n>` con su manifiesto/hash; re-consolidar al
  crecer el crawl.

## Consideraciones éticas
- **Fuente única ESTATAL** (Andina es agencia del Estado peruano) → **sesgo de
  encuadre**; declararlo como amenaza a la validez externa.
- **Personas nombradas** en contextos sensibles (judiciales, políticos): el sistema
  atribuye todo a su fuente y no afirma hechos; las relaciones son interpretables,
  no veredictos.
- **Sesgos del modelo** (NER/LLM) pueden propagarse al grafo.
- **TODO:** revisión ética del curso/institución si aplica.
