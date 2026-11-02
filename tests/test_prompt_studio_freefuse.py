# -*- coding: utf-8 -*-
"""Tests locales de Prompt Studio FreeFuse y Spans FreeFuse (sin API).
Uso:  python3 -m pytest tests/ -q     (o  python3 tests/test_prompt_studio_freefuse.py)
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import test_prompt_studio as base_t  # perfiles ficticios + FakeClient
import rafa_prompt_studio as rps
import rafa_prompt_studio_freefuse as ff

base_t.make_dir()


def run_ff(replies, **over):
    fake = base_t.FakeClient(replies)
    rps.anthropic = types.SimpleNamespace(Anthropic=lambda api_key: fake)
    args = dict(escena="algo", base="basea", lexico="ninguno", personaje_1="alfa", personaje_2="gamma",
                personaje_3="ninguno", personaje_4="ninguno", usar_estetica=True, nsfw="explicit",
                encuadre="auto", estilo="compacto", creatividad=0.8, seed=0, api_key="k",
                modelo_claude="claude-sonnet-4-6", extra="")
    args.update(over)
    return ff.RafaPromptStudioFreeFuse().generar_ff(**args), fake


def reply(setting="Inside a wooden sauna with amber light", p1="sitting at the left of the frame, naked",
          p2="standing at the right of the frame, touching the belly of the man on his left",
          finish="Sharp phone photograph.", **extra):
    d = {"setting": setting, "subjects": {"P1": p1, "P2": p2}, "finish": finish, "negative": "",
         "razonamiento": "ok"}
    d.update(extra)
    return json.dumps(d)


def test_inputs_y_salidas():
    it = ff.RafaPromptStudioFreeFuse.INPUT_TYPES()["required"]
    assert "personaje_4" in it and "variantes" not in it
    keys = list(it)
    assert keys.index("personaje_4") == keys.index("personaje_3") + 1
    assert ff.RafaPromptStudioFreeFuse.RETURN_NAMES[-1] == "freefuse_info"
    # El nodo normal no cambia
    assert rps.RafaPromptStudio.RETURN_NAMES == ("prompt", "negative", "razonamiento")
    assert "personaje_4" not in rps.RafaPromptStudio.INPUT_TYPES()["required"]


def test_montaje_orden_y_spans_literales():
    (prompt, neg, raz, info), fake = run_ff([reply()])
    assert prompt.startswith("Inside a wooden sauna with amber light. Alfa, a heavyset older man, sitting")
    assert prompt.index("Alfa") < prompt.index("Gamma")
    assert "FREEFUSE MODE" in fake.calls[0]["system"][0]["text"]
    r = ff.RafaFreeFuseSpans().spans(prompt, info)[:7]
    _, s1, s2, s3, s4, fondo, informe = r
    assert fondo == "Inside a wooden sauna with amber light"
    assert s1 == "Alfa, a heavyset older man, sitting at the left of the frame, naked"
    assert s2.startswith("Gamma, an obese man, standing") and "photograph" not in s2
    assert s3 == s4 == ""
    for s in (s1, s2, fondo):
        assert s in prompt  # literal, como pide FreeFuse


def test_nombre_de_otro_en_bloque_reintenta():
    malo = reply(p2="standing at the right of the frame, touching Alfa's belly")
    (prompt, _, raz, _), fake = run_ff([malo, reply()])
    assert len(fake.calls) == 2
    assert "Alfa" in fake.calls[1]["messages"][-1]["content"]
    assert prompt.count("Alfa") == 1


def test_class_de_otro_en_bloque_reintenta():
    malo = reply(p2="standing at the right, kissing the heavyset older man")
    (_, _, _, _), fake = run_ff([malo, reply()])
    assert len(fake.calls) == 2


def test_setting_con_personaje_o_marcador_reintenta():
    (_, _, _, _), fake = run_ff([reply(setting="Alfa's sauna"), reply()])
    assert len(fake.calls) == 2
    (_, _, _, _), fake = run_ff([reply(p1="[P1] sitting"), reply()])
    assert len(fake.calls) == 2


def test_problema_persistente_va_a_avisos():
    malo = reply(setting="")
    (prompt, _, raz, info), fake = run_ff([malo, malo])
    assert "Sin corregir" in raz
    _, _, _, _, _, fondo, informe = ff.RafaFreeFuseSpans().spans(prompt, info)[:7]
    assert fondo == "" and "Fondo vacio" in informe


def test_json_invalido_reintenta():
    (prompt, _, _, _), fake = run_ff(["esto no es json", reply()])
    assert len(fake.calls) == 2 and prompt.startswith("Inside")


def test_bloqueo_duro():
    malo = reply(p1="sitting, a young man nearby")
    try:
        run_ff([malo, malo])
        assert False
    except RuntimeError as e:
        assert "young" in str(e)


def test_spans_tras_editar_en_la_puerta():
    (prompt, _, _, info), _ = run_ff([reply()])
    editado = prompt.replace("Inside a wooden sauna", "Inside a dark tiled steam room").replace(
        "naked", "naked, legs spread wide")
    _, s1, s2, _, _, fondo, informe = ff.RafaFreeFuseSpans().spans(editado, info)[:7]
    assert fondo.startswith("Inside a dark tiled steam room")
    assert s1.endswith("legs spread wide") and s1 in editado
    assert "AVISOS" not in informe


def test_spans_orden_cambiado_y_acabado_borrado():
    (prompt, _, _, info), _ = run_ff([reply()])
    a_i, g_i = prompt.index("Alfa"), prompt.index("Gamma")
    fin = prompt.index("Sharp phone")
    a_blk, g_blk = prompt[a_i:g_i], prompt[g_i:fin]
    editado = prompt[:a_i] + g_blk + a_blk  # Gamma primero, sin acabado
    _, s1, s2, _, _, _, informe = ff.RafaFreeFuseSpans().spans(editado, info)[:7]
    assert s1.startswith("Alfa") and s2.startswith("Gamma")
    assert "acabado" in informe


def test_spans_trigger_borrado_da_error():
    (prompt, _, _, info), _ = run_ff([reply()])
    try:
        ff.RafaFreeFuseSpans().spans(prompt.replace("Gamma", "The other man"), info)[:7]
        assert False
    except ValueError as e:
        assert "Gamma" in str(e)


def test_cuatro_personajes():
    d = {"setting": "On a wide bed", "subjects": {f"P{i}": f"lying in zone {i}" for i in range(1, 5)},
         "finish": "Sharp phone photograph.", "negative": "", "razonamiento": ""}
    (prompt, _, _, info), _ = run_ff([json.dumps(d)], personaje_3="beta/A", personaje_4="delta")
    s = ff.RafaFreeFuseSpans().spans(prompt, info)
    assert all(s[1:5]) and json.loads(info)["triggers"] == ["Alfa", "Gamma", "BetaA", "Delta"]
    assert s[4].startswith("Delta, an obese heavyset older man, with a shaved head and a mustache")


def test_is_changed_distinto_del_normal_y_con_p4():
    a = ff.RafaPromptStudioFreeFuse.IS_CHANGED(escena="x", base="basea", personaje_1="alfa")
    b = ff.RafaPromptStudioFreeFuse.IS_CHANGED(escena="x", base="basea", personaje_1="alfa",
                                               personaje_4="gamma")
    assert a != b
    assert a == ff.RafaPromptStudioFreeFuse.IS_CHANGED(escena="x", base="basea", personaje_1="alfa")


def test_adapter_y_plan_reparto():
    assert ff.adapter_de("frypex") == "txr_frypex" and ff.adapter_de("lexte/A") == "txr_lexte_a"
    act = ff.plan_reparto([("ninguno", "ninguno", 1), ("alfa", "a.safetensors", 0.9),
                           ("ninguno", "ninguno", 1), ("gamma", "g.safetensors", 1.0)])
    assert [a["personaje"] for a in act] == ["alfa", "gamma"] and act[0]["fuerza"] == 0.9
    for malo in ([("alfa", "ninguno", 1)], [("ninguno", "x.safetensors", 1)],
                 [("alfa", "a", 1), ("alfa", "b", 1)], [("ninguno", "ninguno", 1)]):
        try:
            ff.plan_reparto(malo)
            assert False, malo
        except ValueError:
            pass


def test_nodo_reparto_encadena_loaders():
    llamadas = []

    class FakeLoader:
        def load_lora(self, model, clip, lora, adapter, sm, sc, ffdata):
            llamadas.append((lora, adapter, sm, sc))
            d = dict(ffdata or {"adapters": []})
            d["adapters"] = list(d.get("adapters", [])) + [adapter]
            return model + 1, clip, d

    sys.modules["nodes"] = types.SimpleNamespace(NODE_CLASS_MAPPINGS={"FreeFuseLoRALoader": FakeLoader})
    kw = {f"personaje_{i}": "ninguno" for i in range(1, 5)}
    kw.update({f"lora_{i}": "ninguno" for i in range(1, 5)})
    kw.update({f"fuerza_{i}": 1.0 for i in range(1, 5)})
    kw.update(personaje_1="gamma", lora_1="g.safetensors", personaje_3="alfa", lora_3="a.safetensors", fuerza_3=0.8)
    model, clip, ffd, reparto = ff.RafaRepartoFreeFuse().cargar(0, "clip", **kw)
    assert model == 2 and ffd["adapters"] == ["txr_gamma", "txr_alfa"]
    assert llamadas[1] == ("a.safetensors", "txr_alfa", 0.8, 0.0)
    assert [x["personaje"] for x in json.loads(reparto)] == ["gamma", "alfa"]


def test_reparto_manda_sobre_widgets_y_spans_dan_adapters():
    rep = json.dumps([{"personaje": "gamma", "adapter": "txr_gamma"}, {"personaje": "alfa", "adapter": "txr_alfa"}])
    d = reply(p1="standing at the left of the frame", p2="sitting at the right of the frame")
    (prompt, _, _, info), _ = run_ff([d], reparto=rep)  # widgets dicen alfa/gamma; manda el reparto
    assert prompt.index("Gamma") < prompt.index("Alfa")
    out = ff.RafaFreeFuseSpans().spans(prompt, info)
    assert len(out) == 11 and out[1].startswith("Gamma") and out[7:] == ("txr_gamma", "txr_alfa", "", "")
    a = ff.RafaPromptStudioFreeFuse.IS_CHANGED(escena="x", base="basea", personaje_1="alfa")
    assert a != ff.RafaPromptStudioFreeFuse.IS_CHANGED(escena="x", base="basea", personaje_1="alfa", reparto=rep)


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f()
            print("ok", n)
