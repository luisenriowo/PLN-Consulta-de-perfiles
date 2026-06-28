"""Tests de la capa multi-fuente (Fase 3, verdades conocidas, sin red).

Valida:
  (1) _familia_fuente: deriva la fuente del doc_id namespaced.
  (2) señal multi_fuente: True solo con ≥2 familias de fuente; y es decisiva
      para la saliencia (§2: ≥2 señales).
  (3) dedup CROSS-FUENTE en preprocess: misma nota en dos medios → una sola.
  (4) dispatcher de colectores: registra andina+gdelt y omite fuentes desconocidas.

Uso:  python scripts/test_multifuente.py
"""

from __future__ import annotations

import importlib.util
from datetime import date

from src.pipeline import preprocess, salience
from src.schemas import Documento, EventCluster


def test_familia_fuente() -> None:
    assert salience._familia_fuente("andina:123456") == "andina"
    assert salience._familia_fuente("gdelt:https://x.pe/n") == "gdelt"
    assert salience._familia_fuente("sinprefijo") == "sinprefijo"
    print("  OK _familia_fuente: deriva la fuente del doc_id")


def test_multi_fuente_decisiva() -> None:
    mono = EventCluster(
        cluster_id="e",
        fecha_normalizada=date(2021, 1, 1),
        pasajes_evidencia=["Evento neutral sin gatillos lexicos"],
        fechas_evidencia=[date(2021, 1, 1)],
        fuentes=["andina:1", "andina:2"],
    )
    multi = EventCluster(
        cluster_id="e",
        fecha_normalizada=date(2021, 1, 1),
        pasajes_evidencia=["Evento neutral sin gatillos lexicos"],
        fechas_evidencia=[date(2021, 1, 1)],
        fuentes=["andina:1", "gdelt:u"],
    )
    assert salience.senales(mono)["multi_fuente"] is False
    assert salience.senales(multi)["multi_fuente"] is True
    # mono: solo nota_dedicada (1 señal) → no saliente; multi: +multi_fuente (2) → saliente
    assert salience.es_saliente(mono) is False
    assert salience.es_saliente(multi) is True
    print("  OK multi_fuente: True con >=2 fuentes y decisiva para la saliencia")


def test_dedup_cross_fuente() -> None:
    txt = (
        "Titular del evento. Cuerpo de la nota con longitud suficiente para "
        "superar el mínimo de caracteres del preprocess y no ser descartada."
    )
    d1 = Documento(
        doc_id="andina:1",
        fuente="andina.pe",
        url="u1",
        fecha_pub=date(2021, 1, 1),
        texto=txt,
    )
    d2 = Documento(
        doc_id="gdelt:https://otromedio.pe/n",
        fuente="otromedio.pe",
        url="u2",
        fecha_pub=date(2021, 1, 2),
        texto=txt,
    )
    out = preprocess.preprocess([d1, d2])
    assert len(out) == 1, out  # misma firma de texto → dedup cross-fuente
    assert out[0].doc_id == "andina:1", out  # gana la primera aparición
    print("  OK dedup cross-fuente: nota republicada en 2 medios -> 1 documento")


def test_byline_stripping() -> None:
    # "(FIN) ..." marca fin de nota: se elimina todo el crédito.
    out = preprocess.limpiar(
        "El ministro habló sobre turismo en Cusco. (FIN) NDP/ETA/JCR JRA : Publicado: 9/9/2025"
    )
    assert "NDP" not in out and "Publicado" not in out, out
    assert "turismo" in out, out
    # variante sin (FIN): iniciales en mayúscula + Publicado: fecha
    out2 = preprocess.limpiar("Texto normal del cuerpo. MCA GRM Publicado: 7/10/2025")
    assert "MCA" not in out2 and "Texto normal" in out2, out2
    # NO borra texto legítimo ("publicado" en minúscula, sin iniciales)
    out3 = preprocess.limpiar(
        "El informe fue publicado el 1/2/2024 por el diario oficial."
    )
    assert "publicado" in out3 and "diario oficial" in out3, out3
    print("  OK byline: elimina créditos NDP/MCA/JCR, conserva texto legítimo")


def test_dispatcher_colectores() -> None:
    spec = importlib.util.spec_from_file_location("pt", "scripts/precompute_tema.py")
    assert spec is not None
    assert spec.loader is not None
    pt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pt)
    assert {"andina", "gdelt"} <= set(pt._COLECTORES), pt._COLECTORES.keys()

    class _Cfg:
        fuentes = ("desconocida",)

    assert pt._colectar(_Cfg()) == []  # fuente desconocida se omite sin crash
    print("  OK dispatcher: registra andina+gdelt, omite fuentes desconocidas")


def main() -> None:
    print("== (1) _familia_fuente ==")
    test_familia_fuente()
    print("\n== (2) señal multi_fuente ==")
    test_multi_fuente_decisiva()
    print("\n== (3) dedup cross-fuente ==")
    test_dedup_cross_fuente()
    print("\n== (4) fix de bylines (preprocess) ==")
    test_byline_stripping()
    print("\n== (5) dispatcher de colectores ==")
    test_dispatcher_colectores()
    print("\n[OK] TODOS LOS TESTS MULTI-FUENTE PASARON")


if __name__ == "__main__":
    main()
