# -*- coding: utf-8 -*-
"""Tests locales de Ideas (Rafa) y Elegir idea (Rafa) (sin API).
Uso:  python3 tests/test_ideas.py
"""
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import test_prompt_studio as base_t
import rafa_prompt_studio as rps
import rafa_ideas as ri

base_t.make_dir()


def nueva_hist():
    d = tempfile.mkdtemp()
    os.environ["RAFA_IDEAS_DIR"] = d
    return os.path.join(d, "historial.jsonl")


def resp(n=3, extra=""):
    return json.dumps({"ideas": [{"titulo": f"Idea {i}", "escena": f"Alfa y Gamma en el sitio {i}{extra}"}
                                 for i in range(1, n + 1)], "comentario": ""})


def run(replies, **over):
    fake = base_t.FakeClient(replies)
    rps.anthropic = types.SimpleNamespace(Anthropic=lambda api_key: fake)
    args = dict(peticion="dame ideas", personaje_1="alfa", personaje_2="gamma", personaje_3="ninguno",
                personaje_4="ninguno", cantidad=3, nsfw="explicit", para_freefuse=True, no_repetir=True,
                usar_estetica=True, creatividad=1.0, seed=0, a_partir_de="", api_key="k")
    args.update(over)
    return ri.RafaIdeas().generar(**args), fake


def test_tanda_formato_lista_e_historial():
    h = nueva_hist()
    (ideas, lista), fake = run([resp()])
    assert ideas.startswith("1. Idea 1 — Alfa y Gamma en el sitio 1")
    assert lista == [f"Alfa y Gamma en el sitio {i}" for i in (1, 2, 3)]
    assert "FREEFUSE" in fake.calls[0]["system"][0]["text"]
    u = fake.calls[0]["messages"][0]["content"]
    assert "Alfa (heavyset older man)" in u and "Gamma (obese man)" in u and "EXACTLY 3" in u
    assert len(open(h).read().strip().splitlines()) == 1


def test_no_repetir_pasa_titulos_previos():
    nueva_hist()
    run([resp()])
    (_, _), fake = run([resp()], seed=1)
    assert "ALREADY GIVEN BEFORE" in fake.calls[0]["messages"][0]["content"]
    (_, _), fake = run([resp()], seed=2, no_repetir=False)
    assert "ALREADY GIVEN BEFORE" not in fake.calls[0]["messages"][0]["content"]


def test_encadenar_con_a_partir_de():
    nueva_hist()
    run([resp()])
    (_, _), fake = run([resp()], a_partir_de="más como la 2 pero en un garaje", seed=5)
    u = fake.calls[0]["messages"][0]["content"]
    assert "YOUR PREVIOUS BATCH" in u and "2. Idea 2 — Alfa y Gamma en el sitio 2" in u
    assert "más como la 2" in u


def test_bloqueo_espanol_reintenta_y_falla():
    nueva_hist()
    (ideas, _), fake = run([resp(extra=", con un chico mirando"), resp()])
    assert len(fake.calls) == 2 and "chico" not in ideas
    try:
        run([resp(extra=" con un joven"), resp(extra=" con un joven")])
        assert False
    except RuntimeError as e:
        assert "joven" in str(e)
    # 'menor' suelto no bloquea ("en menor medida")
    assert ri.terminos_bloqueados("en menor medida") == []
    assert ri.terminos_bloqueados("un menor de edad") == ["menor de edad"]


def test_json_roto_reintenta():
    nueva_hist()
    (ideas, _), fake = run(["nada", resp()])
    assert len(fake.calls) == 2 and ideas.startswith("1.")


def test_elegir():
    texto = ri.formatear([{"titulo": "Sauna", "escena": "Alfa en la sauna"},
                          {"titulo": "", "escena": "Gamma en el garaje"}])
    assert ri.RafaElegirIdea().elegir(texto, 1) == ("Alfa en la sauna",)
    assert ri.RafaElegirIdea().elegir(texto, 2) == ("Gamma en el garaje",)
    try:
        ri.elegir(texto, 5)
        assert False
    except ValueError as e:
        assert "1-2" in str(e)


def test_is_changed_no_depende_del_historial():
    nueva_hist()
    a = ri.RafaIdeas.IS_CHANGED(peticion="x", seed=1)
    run([resp()])
    assert a == ri.RafaIdeas.IS_CHANGED(peticion="x", seed=1)
    assert a != ri.RafaIdeas.IS_CHANGED(peticion="x", seed=2)
    assert ri.RafaIdeas.OUTPUT_IS_LIST == (False, True)


def test_reparto_manda_en_ideas():
    nueva_hist()
    rep = json.dumps([{"personaje": "gamma", "adapter": "txr_gamma"}])
    (_, _), fake = run([resp()], reparto=rep)
    u = fake.calls[0]["messages"][0]["content"]
    assert "Gamma (obese man)" in u and "Alfa" not in u.split("RAFA'S REQUEST")[0]


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
            print("ok", n)
