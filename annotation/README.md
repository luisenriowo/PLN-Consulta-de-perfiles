# Protocolo de anotacion gold

## Archivo a llenar

```text
data/corpus_humala_anotacion.xlsx
```

Usar la hoja:

```text
corpus
```

No editar archivos generados por el sistema en:

```text
data/eventos_humala.parquet
data/salidas/
```

## Objetivo

Construir una linea de tiempo humana de eventos importantes sobre Ollanta Humala usando solo las noticias del corpus.

El gold sirve como referencia para evaluar las salidas automaticas del sistema.

## Columnas informativas

No modificar estas columnas:

```text
doc_id
fecha_pub
titulo
url
lead
fuente
queries
clase_protagonismo
humala_protagonista
```

## Columnas a llenar

### anotar_en_gold

Valores permitidos:

```text
si
no
duda
```

Usar `si` cuando la noticia contiene un evento que debe aparecer en la linea de tiempo final.

Usar `no` cuando la noticia no aporta un evento relevante para la linea de tiempo.

Usar `duda` cuando el anotador no puede decidir.

### fecha_evento_gold

Formato obligatorio:

```text
YYYY-MM-DD
```

Reglas:

- usar la fecha real del evento si la noticia la indica claramente
- si la noticia no indica otra fecha, usar `fecha_pub`
- no usar fechas incompletas
- no inventar fechas

Ejemplo:

```text
2025-04-15
```

### resumen_evento_gold

Escribir un resumen breve del evento.

Reglas:

- una sola oracion
- maximo 35 palabras
- debe mencionar el hecho principal
- debe mencionar a Ollanta Humala si es necesario para entender el evento
- no copiar literalmente el titulo si se puede resumir mejor
- no agregar informacion que no este en la noticia

### notas_anotador

Usar solo para aclaraciones.

Ejemplos:

```text
mismo evento que doc_id andina:832054
fecha del evento no explicita; use fecha_pub
duda: Humala aparece como contexto, no como protagonista
```

## Criterios para marcar `si`

Marcar `si` si la noticia cumple al menos una condicion:

1. Humala es protagonista del hecho.
2. El hecho cambia el estado judicial, politico o publico de Humala.
3. El hecho corresponde a acusacion, juicio, sentencia, prision, investigacion, candidatura, campana, partido, decision judicial o reparacion civil.
4. La noticia resume un hito relevante de un caso asociado a Humala.

## Criterios para marcar `no`

Marcar `no` si:

1. Humala solo aparece mencionado como contexto.
2. El evento principal es sobre otra persona.
3. La noticia es una opinion menor sin hecho nuevo.
4. La noticia repite exactamente un evento ya anotado y no agrega informacion nueva.
5. La noticia no permite identificar un evento concreto.

## Noticias del mismo evento

Si varias noticias cubren el mismo evento:

1. Marcar `si` solo en la fila mas clara o completa.
2. Marcar `no` en las repetidas.
3. En `notas_anotador`, indicar el `doc_id` de la fila principal.

Ejemplo:

```text
mismo evento que doc_id andina:832054
```

## Reglas anti-circularidad

No usar como referencia:

```text
data/eventos_humala.parquet
data/salidas/b0_lead.json
data/salidas/b1_extractive.json
```

No copiar eventos producidos por el sistema.

El gold debe salir de:

```text
fecha_pub
titulo
url
lead
```

Si hace falta contexto, abrir la URL de la noticia.

## Ejemplo

| anotar_en_gold | fecha_evento_gold | resumen_evento_gold | notas_anotador |
|---|---|---|---|
| si | 2025-04-15 | El Poder Judicial dicto sentencia contra Ollanta Humala y Nadine Heredia por el caso Odebrecht. | fecha tomada de fecha_pub |

## Cierre de anotacion

Al terminar:

1. guardar el archivo como `.xlsx`
2. no cambiar nombres de columnas
3. no eliminar filas
4. entregar el archivo anotado para congelarlo en:

```text
annotation/gold/
```
