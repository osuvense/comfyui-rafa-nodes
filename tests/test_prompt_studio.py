# -*- coding: utf-8 -*-
"""Tests locales de RafaPromptStudio, con perfiles ficticios y cliente simulado (sin API).
Uso:  python3 -m pytest tests/ -q     (o  python3 tests/test_prompt_studio.py)
"""
import json
import os
import sys
import tempfile
import types
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rps", os.path.join(HERE, "..", "rafa_prompt_studio.py"))
rps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rps)

MODELO = """---
id: basea
nombre: Base A
familia_lora: famA
negative: false
---
# Base A
## Reglas
- Long prose.
## Historial
- SECRETO-HISTORIAL
"""
MODELO_NEG = """---
id: baseb
nombre: Base B
negative: true
---
# Base B
"""
LEX = """---
id: lexx
nombre: Lex X
bases: [basea]
---
# Lex
- term one
"""
P_ALFA = """---
id: alfa
trigger: Alfa
class: heavyset older man
reservado: ["heavyset older man"]
loras:
  - base: famA
    entrenamiento: ALFA_1
acabado_pedir: "Sharp phone photograph."
acabado_evitar: ["Low-resolution video frame"]
---
# Alfa
Example: Alfa, a <CLASS>, sitting.
## Historial
- SECRETO
"""
P_BETA = """---
id: beta
trigger: Beta
class: heavyset older man
variantes:
  A: {trigger: BetaA}
  B: {trigger: BetaB, class: "elderly bald man"}
loras:
  - base: basea
---
# Beta
"""
P_GAMMA = """---
id: gamma
trigger: Gamma
class: obese man
---
# Gamma
"""
ESTETICA = """---
id: estetica
---
# Estetica
Default subject: a mature adult man.
"""


def make_dir():
    d = tempfile.mkdtemp()
    files = {"modelos/basea.md": MODELO, "modelos/baseb.md": MODELO_NEG, "modelos/_borrador.md": MODELO,
             "lexicos/lexx.md": LEX, "personajes/alfa.md": P_ALFA, "personajes/beta.md": P_BETA,
             "personajes/gamma.md": P_GAMMA, "estetica.md": ESTETICA}
    for rel, txt in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(txt)
    os.environ["RAFA_PERFILES_DIR"] = d
    return d


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0)
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=text)],
            usage=types.SimpleNamespace(input_tokens=10, output_tokens=5,
                                        cache_creation_input_tokens=0, cache_read_input_tokens=0))


def run_node(replies, **over):
    fake = FakeClient(replies)
    rps.anthropic = types.SimpleNamespace(Anthropic=lambda api_key: fake)
    args = dict(escena="algo", base="basea", lexico="ninguno", personaje_1="alfa",
                personaje_2="ninguno", personaje_3="ninguno", usar_estetica=True, nsfw="explicit",
                encuadre="auto", estilo="caption", variantes=1, creatividad=0.8, seed=0,
                api_key="k", modelo_claude="claude-sonnet-4-6", extra="")
    args.update(over)
    return rps.RafaPromptStudio().generar(**args), fake


def J(prompt, negative="", variants=None, raz="ok"):
    return json.dumps({"prompt": prompt, "negative": negative, "variants": variants or [], "razonamiento": raz})


# ---------------- tests ----------------

def test_listados():
    make_dir()
    it = rps.RafaPromptStudio.INPUT_TYPES()["required"]
    assert it["base"][0] == ["basea", "baseb"]          # _borrador ignorado
    assert it["lexico"][0] == ["ninguno", "lexx"]
    assert it["personaje_1"][0] == ["ninguno", "alfa", "beta", "beta/A", "beta/B", "gamma"]


def test_montaje_basico_y_acabado():
    make_dir()
    (prompt, neg, raz), fake = run_node([J("[P1], lying on a bed. [P1]'s hand rests on his belly. Warm light")])
    assert prompt.startswith("Alfa, a heavyset older man, lying on a bed. Alfa's hand")
    assert prompt.endswith("Warm light. Sharp phone photograph.")
    assert neg == ""
    system = fake.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "SECRETO" not in system[0]["text"]           # Historial fuera
    assert "Alfa, a heavyset older man, sitting" in system[0]["text"]  # <CLASS> sustituido
    assert "Default subject" in system[0]["text"]


def test_bloqueo_duro_con_reintento_ok():
    make_dir()
    (prompt, _, _), fake = run_node([J("[P1] with a young man"), J("[P1] with another adult man")])
    assert len(fake.calls) == 2 and "young" not in prompt.lower()


def test_bloqueo_duro_persistente():
    make_dir()
    try:
        run_node([J("[P1] with a teenager"), J("[P1], youthful face")])
    except RuntimeError as e:
        assert "bloqueado" in str(e)
    else:
        raise AssertionError("debia bloquear")


def test_bloqueo_en_negative():
    make_dir()
    try:
        run_node([J("[P1] sits", negative="young"), J("[P1] sits", negative="boy")], base="baseb")
    except RuntimeError:
        pass
    else:
        raise AssertionError("debia bloquear el negative")


def test_marcador_que_falta_reintenta():
    make_dir()
    (prompt, _, raz), fake = run_node([J("a man sits"), J("[P1] sits")])
    assert len(fake.calls) == 2
    assert prompt.startswith("Alfa, a heavyset older man sits")


def test_avisos_class_compartida_y_reservada():
    make_dir()
    (prompt, _, raz), _ = run_node(
        [J("[P1] at the left of the frame, [P2] at the right, and a heavyset older man behind")],
        personaje_2="beta/A")
    assert "comparten class" in raz
    assert "aparece 3 veces" in raz


def test_variante_sobrescribe_y_sin_lora():
    make_dir()
    (prompt, _, raz), _ = run_node([J("[P1] stands")], personaje_1="beta/B", base="baseb")
    assert prompt.startswith("BetaB, an elderly bald man stands")
    assert "no tiene LoRA para la base" in raz


def test_huecos_compactados_y_marcador_sobrante():
    make_dir()
    (prompt, _, raz), _ = run_node([J("[P1] and [P2] kiss. [P3] watches")],
                                   personaje_1="ninguno", personaje_2="alfa", personaje_3="gamma")
    assert prompt.startswith("Alfa, a heavyset older man and Gamma, an obese man kiss.")
    assert "[P3] sin personaje" in raz


def test_negative_segun_base():
    make_dir()
    (_, neg, _), _ = run_node([J("[P1] sits", negative="blurry")])
    assert neg == ""
    (_, neg, _), _ = run_node([J("[P1] sits", negative="blurry")], base="baseb")
    assert neg == "blurry"


def test_variantes():
    make_dir()
    (prompt, _, raz), _ = run_node([J("[P1] sits", variants=["[P1] sits", "[P1] kneels"])], variantes=2)
    assert "VARIANTES" in raz and "Alfa, a heavyset older man kneels" in raz


def test_acabado_evitar_y_compacto():
    make_dir()
    (prompt, _, raz), _ = run_node([J("[P1] sits. Low-resolution video frame.")], estilo="compacto")
    assert not prompt.endswith("Sharp phone photograph.")
    assert "pide evitar" in raz


def test_is_changed_incluye_perfiles():
    d = make_dir()
    kw = dict(escena="x", base="basea", personaje_1="alfa", seed=1)
    a = rps.RafaPromptStudio.IS_CHANGED(**kw)
    assert a == rps.RafaPromptStudio.IS_CHANGED(**kw)
    assert a != rps.RafaPromptStudio.IS_CHANGED(**dict(kw, seed=2))
    assert a == rps.RafaPromptStudio.IS_CHANGED(**dict(kw, api_key="otra"))
    with open(os.path.join(d, "personajes", "alfa.md"), "a") as fh:
        fh.write("\nnuevo dato\n")
    assert a != rps.RafaPromptStudio.IS_CHANGED(**kw)


def test_temperature_sdk_v1_por_extra_body():
    make_dir()
    rps._SDK_HAS_TEMPERATURE = False
    (_, _, _), fake = run_node([J("[P1] sits")])
    assert "temperature" not in fake.calls[0] and fake.calls[0]["extra_body"]["temperature"] == 0.8
    (_, _, _), fake = run_node([J("[P1] sits")], modelo_claude="claude-sonnet-5")
    assert "temperature" not in fake.calls[0] and "extra_body" not in fake.calls[0]
    rps._SDK_HAS_TEMPERATURE = None


def test_lexico_fuera_de_base():
    make_dir()
    (_, _, raz), fake = run_node([J("[P1] sits")], lexico="lexx", base="baseb")
    assert "no esta declarado" in raz
    assert "term one" in fake.calls[0]["system"][0]["text"]


def test_json_con_fences_y_ruido():
    make_dir()
    (prompt, _, _), _ = run_node(["```json\n" + J("[P1] sits") + "\n```"])
    assert prompt.startswith("Alfa")


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
