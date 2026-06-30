from __future__ import annotations

import json
from pathlib import Path


SRC = Path("andina_crawl_new/andina_crawl.jsonl")
DST = Path("andina_crawl_new/andina_crawl_2025_plus.jsonl")
DESDE = "2025-01-01"


def main() -> None:
    total = 0
    validas = 0
    descartadas = 0

    with SRC.open(encoding="utf-8", errors="replace") as fin, DST.open(
        "w", encoding="utf-8"
    ) as fout:
        for line in fin:
            total += 1
            try:
                obj = json.loads(line)
            except Exception:
                descartadas += 1
                continue
            if obj.get("fecha_pub", "") >= DESDE:
                fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                validas += 1

    print(f"salida: {DST}")
    print(f"lineas leidas: {total}")
    print(f"lineas filtradas (>= {DESDE}): {validas}")
    print(f"lineas descartadas por JSON invalido: {descartadas}")


if __name__ == "__main__":
    main()
