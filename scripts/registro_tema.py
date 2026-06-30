from src import manifiesto
from src.storage import KnowledgeGraph

slug = "andina-2025"
nombre = "Andina 2025+ — grafo abierto"

with KnowledgeGraph(slug, read_only=True) as g:
    entidades = g.entities()
    relaciones = g.relations()
    fechas = []
    for r in relaciones:
        fecha = r.get("fecha")
        if fecha is None:
            continue
        if hasattr(fecha, "date"):
            fecha = fecha.date()
        if hasattr(fecha, "isoformat"):
            fecha = fecha.isoformat()
        else:
            fecha = str(fecha)
        fechas.append(fecha)

entrada = manifiesto.actualizar_tema(
    slug,
    nombre,
    n_entidades=len(entidades),
    n_relaciones=len(relaciones),
    rango_fechas=[min(fechas), max(fechas)] if fechas else None,
)

print(entrada)
