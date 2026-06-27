"""Esquemas de datos compartidos por todo el pipeline.

Estos modelos son el contrato de datos del sistema. Son CASI inmutables:
cualquier cambio aquí afecta a las cuatro condiciones por igual y, por tanto,
afecta la comparación. Mantén los campos fieles a  §5.

Nada de lógica de negocio vive aquí: solo estructura y validación.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Taxonomía de relaciones — fuente única de verdad.
# Importar desde aquí; no redefinir en otros módulos.
# ---------------------------------------------------------------------------
TIPOS_RELACION: dict[str, str] = {
    "alianza":          "Apoyo, colaboración o respaldo mutuo",
    "conflicto":        "Oposición, enfrentamiento o rechazo",
    "pertenencia":      "Miembro de, afiliado a, parte de",
    "nombramiento":     "Designación, nombramiento o elección de un cargo",
    "acusacion":        "Imputación, acusación o investigación judicial",
    "ruptura":          "Alejamiento, renuncia o expulsión de una relación previa",
    "mencion":          "Co-aparición sin relación claramente identificable",
}


class EntidadMencion(BaseModel):
    """Una mención de entidad detectada por NER y resuelta por entity linking.

    `entidad_id` es el identificador canónico tras la resolución (p. ej.
    "humala:ollanta"); queda en None cuando la mención no se pudo enlazar a una
    entidad conocida del gazetteer. Es lo que resuelve la ambigüedad
    Humala/Antauro/Nadine exigida por .
    """

    texto: str
    tipo: str  # PER, ORG, LOC, MISC (etiquetas spaCy)
    inicio: int  # offset de carácter en Documento.texto
    fin: int
    entidad_id: str | None = None
    entidad_nombre: str | None = None


class Documento(BaseModel):
    """Una noticia cruda ingerida del corpus.

    `fecha_pub` actúa como DCT (Document Creation Time): es el ancla que la
    normalización temporal (HeidelTime) usa para resolver expresiones
    relativas ("ayer", "el lunes pasado") a fechas absolutas.

    `entidades` lo rellena el backbone (pipeline/entities.py); empieza vacío en
    la ingesta. Campo aditivo: no afecta la interfaz del punto de swap.

    Contrato MULTI-FUENTE (invariante de ingesta):
      - `doc_id` DEBE estar namespaced por fuente: ``<fuente>:<id>`` (p. ej.
        "andina:123456", "gdelt:https://..."). Así el id es globalmente único
        aunque dos medios reusen numeraciones internas iguales.
      - `fuente` identifica el medio (dominio): "andina.pe", "gdelt", etc.
      - Una misma nota republicada por dos medios se deduplica en
        `preprocess.preprocess` por FIRMA DE TEXTO (cross-fuente), de modo que
        cuenta una sola vez. Cada colector de ingesta debe respetar este
        contrato para que el corpus sea combinable entre fuentes.
    """

    doc_id: str
    fuente: str
    url: str
    fecha_pub: date
    texto: str
    entidades: list[EntidadMencion] = Field(default_factory=list)


class EventCluster(BaseModel):
    """Un evento candidato, agrupado por correferencia entre documentos.

    Es la ENTRADA del punto de swap: las cuatro condiciones de generación
    reciben exactamente la misma `list[EventCluster]`. `pasajes_evidencia`
    es lo que el Sistema (RAG) usa para anclar; la Ablación lo ignora.
    """

    cluster_id: str
    fecha_normalizada: date
    pasajes_evidencia: list[str] = Field(default_factory=list)
    fuentes: list[str] = Field(default_factory=list)
    # Aditivo: fechas de publicación de las notas miembro. Lo usa salience.py
    # para la señal "cobertura sostenida" (§2). No afecta la interfaz del swap.
    fechas_evidencia: list[date] = Field(default_factory=list)


class EntityNode(BaseModel):
    """Entidad descubierta del corpus — nodo del grafo de conocimiento.

    `entity_id` es el identificador canónico: QID de Wikidata cuando se pudo
    enlazar ("Q6093206"), slug normalizado cuando no ("castillo-pedro").
    `metadata` almacena datos extra de Wikidata (cargo, partido, etc.) sin
    forzar un schema rígido que rompería si Wikidata amplía sus datos.
    """

    entity_id:   str
    nombre:      str
    tipo:        str                                    # PER | ORG | LOC
    alias:       list[str]               = Field(default_factory=list)
    wikidata_id: str | None               = None
    n_docs:      int                      = 0
    n_menciones: int                      = 0
    metadata:    dict                     = Field(default_factory=dict)


class RelationResult(BaseModel):
    """Resultado de clasificar la relación entre dos entidades en una oración.

    Es la salida del RelationClassifier y la entrada para construir RelationEdge.
    `metodo` preserva la trazabilidad: saber si fue reglas o LLM permite
    filtrar por calidad al analizar los resultados.
    """

    tipo:       str     # clave de TIPOS_RELACION
    confianza:  float   # 0.0 – 1.0
    evidencia:  str     # oración de respaldo
    metodo:     str     # "rules" | "llm" | "hybrid"


class RelationEdge(BaseModel):
    """Arista del grafo: relación tipificada entre dos entidades en un período.

    `cluster_id` enlaza de vuelta al EventCluster que generó la relación,
    permitiendo cruzar el grafo con la línea de tiempo existente.
    """

    origen_id:  str
    destino_id: str
    tipo:       str
    fecha:      date
    evidencia:  list[str] = Field(default_factory=list)   # oraciones de respaldo
    fuentes:    list[str] = Field(default_factory=list)   # doc_ids
    confianza:  float
    metodo:     str
    cluster_id: str | None = None


class TimelineEntry(BaseModel):
    """Una entrada de la línea de tiempo generada.

    Es la SALIDA del punto de swap, idéntica en forma para las cuatro
    condiciones. `fuentes` es obligatorio por la invariante de atribución
    (§2.6): ningún evento se afirma sin pasaje fuente que lo respalde.
    """

    fecha: date
    resumen: str
    fuentes: list[str] = Field(default_factory=list)
    confianza: float | None = None
    # Provenancia: el EventCluster que originó la entrada. Es la clave para
    # cruzar las 4 condiciones en la comparación (cada condición emite una
    # entrada por cluster); `fecha`/`fuentes` no son claves fiables porque
    # condiciones distintas pueden citar subconjuntos de fuentes distintos.
    cluster_id: str | None = None
