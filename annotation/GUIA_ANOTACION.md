# Guía de anotación — Gold de entidades y relaciones

Este documento fija las **convenciones de etiquetado** del proyecto. Son parte de
la metodología: el gold y las métricas que se reportan dependen de estas reglas,
así que deben estar escritas (no en la cabeza del anotador) y ser aplicadas por
igual por cualquier anotador.

> **Estado:** v1, redactada por el anotador A (borrador). Pendiente de validar con
> un segundo anotador (acuerdo inter-anotador, ver `scripts/acuerdo_anotadores.py`)
> y de revisión por el responsable del proyecto (Erasmo) en los puntos marcados
> con ⚠ DECISIÓN.

---

## 1. Gold de ENTIDADES (`annotation/gold_entidades/<slug>.csv`)

Cada fila es una entidad descubierta. Se completan tres columnas:

### `es_actor_gold` ∈ {1, 0}
`1` si es un **actor político** real; `0` si no.

- **Actor (1):** persona pública (PER), partido o alianza electoral, institución
  pública u organismo del Estado (Congreso, Consejo de Ministros, ministerios,
  Policía Nacional, Fuerzas Armadas, JNE, ONPE, Poder Ejecutivo, Presidencia…).
- **No actor (0):**
  - Lugares (Lima, Cusco, Arequipa, regiones) → `LOC`.
  - Términos genéricos: "Estado", "Ley", "Gobierno", "República", "Nación".
  - Eventos: "Elecciones 2026".
  - Conectores / basura de NER: "Asimismo", "may" (mes cortado).
  - **Bylines de redacción**: iniciales de redactor + "Publicado" (p. ej.
    "NDP", "FHG", "HTC", "JCR", "CVC JRA Publicado"). NO son entidades.

### `tipo_correcto` ∈ {PER, ORG, LOC, MISC}
El tipo **verdadero**, aunque `es_actor_gold=0` (mide el error de tipado del NER).
Ej.: un ministerio mal tipado como `LOC` por el NER se anota `tipo_correcto=ORG`.

### `nombre_canonico`
Nombre normalizado del actor (déjalo vacío para no-actores). **Si dos filas son
el mismo actor**, ponles el **mismo** `nombre_canonico`: así se detecta un *split*
(actor partido en varios nodos). Ej.: "Comercio Exterior y Turismo" y "Ministerio
de Comercio Exterior" → ambos `Ministerio de Comercio Exterior y Turismo`.

---

## 2. Gold de RELACIONES (`annotation/gold_relaciones/<slug>.csv`)

Se completa `tipo_gold` con la relación **entre `entity_a` y `entity_b`** tal como
la expresa la `oracion`. Ignora la columna `tipo_sugerido` (pista automática).

### Regla central
**La relación debe darse entre las DOS entidades del par.** Si la oración solo las
co-menciona (lista, encuesta, titular de navegación "Lee también"), o la relación
es con un tercero que no es ninguna de las dos, → **`mencion`**.

### Taxonomía (7 tipos)
| tipo | criterio |
|---|---|
| `alianza` | apoyo, respaldo o colaboración mutua explícita |
| `conflicto` | oposición, enfrentamiento, rechazo, crítica |
| `pertenencia` | "X del partido Y", "candidato/lideresa de Y", "milita en Y", "miembro del gabinete" |
| `nombramiento` | "X nombró/juramentó/designó/eligió a Y para un cargo" |
| `acusacion` | imputación, denuncia o investigación judicial |
| `ruptura` | renuncia, expulsión, alejamiento de una relación previa |
| `mencion` | co-aparecen sin relación clara entre ELLAS |

### Reglas de desambiguación (fijadas; ⚠ = validar con Erasmo)
1. **Rivalidad electoral:** neutral → `mencion`. "pasan a segunda vuelta",
   "debate entre X y Y", listas de candidatos/planchas, encuestas (Ipsos, ONPE %)
   son `mencion`. Solo `conflicto` si hay confrontación explícita: "se
   enfrentarán", "criticó", "rechazó", "cuestionó". ⚠ DECISIÓN: ¿la rivalidad de
   segunda vuelta debería ser `conflicto` por defecto? (cambia varios casos)
2. **Co-acusados:** si ambas entidades son investigadas/denunciadas en el mismo
   proceso → `acusacion`. ⚠ DECISIÓN: ¿co-acusados es `acusacion` o `mencion`?
   (no hay acusación *entre* ellas; comparten contexto judicial).
3. **Pertenencia institucional:** "ministro de Comercio Exterior, [X]" como parte
   de un gabinete → `pertenencia` (X ∈ gabinete/Consejo de Ministros).
4. **Falsos enlaces de NER:** si una de las entidades está mal enlazada (p. ej.
   "Roberto" = Roberto Burneo del JNE, no Roberto Sánchez) → `mencion`.
5. **Byline / lista / créditos** → `mencion`.
6. **Oración cortada o ininteligible** → dejar `tipo_gold` **vacío** (se omite del
   cálculo).

---

## 3. Protocolo de acuerdo inter-anotador

1. El anotador A produce el gold completo siguiendo esta guía.
2. Se genera una copia en blanco de una **muestra** (≥30 filas) para el anotador
   B: `uv run python scripts/acuerdo_anotadores.py --blank <gold.csv> --n 30`.
3. B etiqueta la muestra **sin ver** las etiquetas de A.
4. Se mide acuerdo: `uv run python scripts/acuerdo_anotadores.py <A.csv> <B.csv> --col tipo_gold`.
   Reporta % de acuerdo y κ de Cohen.
5. Las discrepancias se discuten; si revelan ambigüedad de criterio, se actualiza
   esta guía (y se vuelve a 1 si el cambio es grande).

Solo tras fijar las convenciones y medir acuerdo se reportan los números finales.
