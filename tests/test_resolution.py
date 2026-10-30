# -*- coding: utf-8 -*-
"""Tests locales de RafaResolution con perfiles ficticios.
Uso:  python3 -m pytest tests/ -q     (o  python3 tests/test_resolution.py)
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import rafa_resolution as rr  # noqa: E402

M1 = """---
id: m1
nombre: Modelo Uno
resoluciones:
  - [1360, 1024]
  - [832, 1248, retrato]
  - [10]
  - [a, b]
---
# M1
"""
M2 = """---
id: m2
nombre: Modelo Dos
---
# sin resoluciones
"""


def make_dir(files):
    d = tempfile.mkdtemp()
    for rel, txt in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(txt)
    os.environ["RAFA_PERFILES_DIR"] = d
    return d


def test_opciones_desde_perfiles():
    make_dir({"modelos/m1.md": M1, "modelos/m2.md": M2, "modelos/_x.md": M1})
    assert rr.opciones() == ["Modelo Uno — 1360×1024", "Modelo Uno — 832×1248 (retrato)"]
    req = rr.RafaResolution.INPUT_TYPES()["required"]
    assert req["resolucion"][0] == rr.opciones()


def test_sin_perfiles():
    os.environ["RAFA_PERFILES_DIR"] = tempfile.mkdtemp()
    old = rr.SIN_PERFILES
    assert rr.opciones() == [old]


def test_resolver_y_orientacion():
    n = rr.RafaResolution()
    assert n.resolver("Modelo Uno — 1360×1024") == (1360, 1024)
    assert n.resolver("Modelo Uno — 1360×1024", "vertical") == (1024, 1360)
    assert n.resolver("Modelo Uno — 832×1248 (retrato)", "horizontal") == (1248, 832)
    assert n.resolver("Modelo Uno — 832×1248 (retrato)", "tal cual") == (832, 1248)


def test_resolver_no_lee_archivos():
    os.environ["RAFA_PERFILES_DIR"] = "/no/existe"
    assert rr.RafaResolution().resolver("Cualquiera — 1024×1024") == (1024, 1024)


def test_etiqueta_mala():
    try:
        rr.RafaResolution().resolver("(sin perfiles)")
    except ValueError:
        return
    raise AssertionError("debia fallar")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
