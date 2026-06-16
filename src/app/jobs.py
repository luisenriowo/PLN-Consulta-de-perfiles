"""Jobs en background para precomputar figuras desde la web.

El precómputo (scraping + LLM) toma minutos: JAMÁS corre dentro del request. La
API lanza este módulo como SUBPROCESO desacoplado (`python -m src.app.jobs
<slug>`), que escribe estado + log a `data/jobs/`. La web hace polling del
estado.

Imports de tope LIGEROS (json/subprocess/stdlib): la API importa este módulo y
no debe arrastrar spaCy/torch. El backbone se importa DENTRO de `ejecutar`, que
corre en el subproceso.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

JOBS = Path("data/jobs")


def slugify(nombre: str) -> str:
    """'Pedro Castillo' -> 'pedro-castillo' (minúsculas, sin acentos, guiones)."""
    base = "".join(
        c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn"
    )
    limpio = "".join(c if c.isalnum() else "-" for c in base.lower())
    return "-".join(p for p in limpio.split("-") if p)


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _estado_path(slug: str) -> Path:
    return JOBS / f"{slug}.json"


def _log_path(slug: str) -> Path:
    return JOBS / f"{slug}.log"


def _params_path(slug: str) -> Path:
    return JOBS / f"{slug}.params.json"


def leer_estado(slug: str) -> dict | None:
    p = _estado_path(slug)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def escribir_estado(slug: str, **kw) -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    actual = leer_estado(slug) or {"slug": slug}
    actual.update(kw)
    _estado_path(slug).write_text(json.dumps(actual, ensure_ascii=False), encoding="utf-8")


def _tail(slug: str, n: int = 5) -> list[str]:
    p = _log_path(slug)
    if not p.exists():
        return []
    lineas = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    return lineas[-n:]


def estado(slug: str) -> dict:
    """Estado del job + últimas líneas del log (para mostrar progreso)."""
    e = leer_estado(slug) or {"slug": slug, "estado": "desconocido"}
    e["log"] = _tail(slug)
    return e


def lanzar(slug: str, nombre: str, homonimos: list[str], terminos: list[str]) -> None:
    """Lanza el precómputo como subproceso desacoplado y deja estado 'running'."""
    JOBS.mkdir(parents=True, exist_ok=True)
    _params_path(slug).write_text(
        json.dumps({"slug": slug, "nombre": nombre, "homonimos": homonimos,
                    "terminos": terminos}, ensure_ascii=False),
        encoding="utf-8",
    )
    escribir_estado(slug, nombre=nombre, estado="running", inicio=_ahora(), fin=None, error=None)
    log = open(_log_path(slug), "w", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "src.app.jobs", slug],
        stdout=log, stderr=subprocess.STDOUT, cwd=str(Path.cwd()),
    )
    log.close()   # el hijo conserva su propio descriptor


def ejecutar(slug: str) -> None:
    """Corre EN el subproceso: arma la config, la persiste y precomputa."""
    from src import figuras
    from scripts.precompute_figura import precompute

    params = json.loads(_params_path(slug).read_text(encoding="utf-8"))
    try:
        cfg = figuras.construir_config(
            slug, params["nombre"], params.get("homonimos", []), params.get("terminos", [])
        )
        figuras.guardar_dinamica(cfg)
        precompute(slug)
        escribir_estado(slug, estado="done", fin=_ahora())
    except Exception as e:   # noqa: BLE001
        import traceback
        traceback.print_exc()
        escribir_estado(slug, estado="error", fin=_ahora(), error=str(e))


if __name__ == "__main__":
    ejecutar(sys.argv[1])
