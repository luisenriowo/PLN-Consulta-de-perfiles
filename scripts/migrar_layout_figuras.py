"""Migra las salidas planas de Humala al layout por-figura + crea el manifiesto.

Una sola vez: mueve data/salidas/{cond}.json -> data/salidas/humala/{cond}.json
y registra la figura en data/figuras.json. No regenera nada. Idempotente.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from src import manifiesto

SALIDAS = Path("data/salidas")
SLUG, NOMBRE = "humala", "Ollanta Humala"


def main() -> None:
    destino = manifiesto.salidas_dir(SLUG)
    destino.mkdir(parents=True, exist_ok=True)
    movidos = 0
    for cond in manifiesto.CONDICIONES:
        plano = SALIDAS / f"{cond}.json"
        if plano.exists():
            shutil.move(str(plano), str(destino / f"{cond}.json"))
            movidos += 1
    print(f"salidas movidas a {destino}/: {movidos}")

    if not manifiesto.corpus_path(SLUG).exists():
        print(f"⚠ falta {manifiesto.corpus_path(SLUG)} (el corpus de la figura)")
    entrada = manifiesto.actualizar(SLUG, NOMBRE)
    print(f"manifiesto actualizado: {entrada}")


if __name__ == "__main__":
    main()
