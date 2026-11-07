# -*- coding: utf-8 -*-
"""Tests locales de la receta y de Prompt de video (Rafa) (sin API ni ComfyUI).
Uso:  python3 tests/test_video.py
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
import rafa_receta as rr
import rafa_video as rv

PERF = base_t.make_dir()
REG_DIR = tempfile.mkdtemp()
os.environ["RAFA_RECETAS_DIR"] = REG_DIR
REG = os.path.join(REG_DIR, "prompt_studio.jsonl")

OK = 0


def check(cond, msg):
    global OK
    if not cond:
        raise AssertionError(msg)
    OK += 1


STUDIO_INPUTS = dict(escena="Alfa se folla a Gamma en un sofa", base="basea", lexico="ninguno",
                     personaje_1="alfa", personaje_2="gamma", personaje_3="ninguno", usar_estetica=True,
                     nsfw="explicit", encuadre="auto", estilo="caption", variantes=1, creatividad=0.8, seed=7,
                     modelo_claude="claude-sonnet-4-6", extra="", nombrar_rasgos_fijos=True)


def grafo(studio_inputs, extra_nodes=None):
    g = {"3": {"class_type": "RafaPromptStudio", "inputs": dict(studio_inputs, api_key="")},
         "4": {"class_type": "CLIPTextEncode", "inputs": {"text": ["3", 0], "clip": ["1", 1]}},
         "5": {"class_type": "KSampler", "inputs": {"seed": 1234, "model": ["1", 0]}},
         "6": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "FRYPEX_KREA1.safetensors",
                                                               "strength_model": 0.9}}}
    g.update(extra_nodes or {})
    return {"prompt": json.dumps(g)}


# ---------- receta: registro y busqueda ----------
rr.registrar_studio("RafaPromptStudio", STUDIO_INPUTS, "PROMPT-A", "")
rr.registrar_studio("RafaPromptStudio", dict(STUDIO_INPUTS, seed=8), "PROMPT-B", "")
rec = rr.extraer_receta(grafo(STUDIO_INPUTS))
check(rec["origen"] == "studio+registro", rec)
check(rec["prompt"] == "PROMPT-A", rec)
check(rec["escena"].startswith("Alfa"), rec)
check(rec["personajes"] == ["alfa", "gamma"], rec)
check(rec["seed"] == 1234 and rec["loras"][0]["fuerza"] == 0.9, rec)

# escena enlazada (Elegir idea): se recupera del registro
linked = dict(STUDIO_INPUTS, escena=["9", 0])
rec = rr.extraer_receta(grafo(linked))
check(rec["prompt"] in ("PROMPT-A",), rec)
check(rec["escena"].startswith("Alfa"), "escena recuperada del registro")
# dos registros que solo cambian la escena -> ambiguo, el mas reciente y aviso
rr.registrar_studio("RafaPromptStudio", dict(STUDIO_INPUTS, escena="otra escena"), "PROMPT-C", "")
rec = rr.extraer_receta(grafo(linked))
check(rec["prompt"] == "PROMPT-C" and any("registros encajan" in a for a in rec["avisos"]), rec)

# sin registro -> escena como intencion
rec = rr.extraer_receta(grafo(dict(STUDIO_INPUTS, seed=99)))
check(rec["origen"] == "studio" and rec["prompt"] == "" and rec["escena"], rec)

# sin Studio: texto literal del encoder (el mas largo = positivo)
g = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a man on a bed, explicit, long prompt here"}},
     "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}}}
rec = rr.extraer_receta({"prompt": json.dumps(g)})
check(rec["origen"] == "grafo" and rec["prompt"].startswith("a man"), rec)

# receta explicita (la app)
rec = rr.extraer_receta({"rafa_receta": json.dumps({"escena": "E", "prompt": "P"})})
check(rec["origen"] == "receta" and rec["prompt"] == "P", rec)

# PNG real con chunks
from PIL import Image, PngImagePlugin
png = os.path.join(REG_DIR, "x.png")
meta = PngImagePlugin.PngInfo()
meta.add_text("prompt", grafo(STUDIO_INPUTS)["prompt"])
Image.new("RGB", (8, 8)).save(png, pnginfo=meta)
rec = rr.receta_de_png(png)
check(rec["prompt"] == "PROMPT-A" and rec["archivo"] == "x.png", rec)

# ---------- prompt de video ----------
check(rv.terminos_bloqueados("un chaval") == ["chaval"], "bloqueo ES")
check("young" in rv.terminos_bloqueados("young man"), "bloqueo EN")

neg = rv.montar_negative(rv.WAN_NEG_DEFAULT, "woman, breasts", grupo=True)
check(rv.WAN_NEG_GRUPO not in neg and neg.endswith("woman, breasts"), neg)
neg = rv.montar_negative(rv.WAN_NEG_DEFAULT, "", grupo=False)
check(rv.WAN_NEG_GRUPO in neg, "solo: se queda")

receta = rr.extraer_receta(grafo(STUDIO_INPUTS))
pet = rv.construir_peticion(receta, "que se la meta más rápido", "fija", "intensa", "explicit", 3.4, True)
check("Rafa's original scene request" in pet and "static camera" in pet and "fast" in pet, pet)
pet = rv.construir_peticion({}, "", "auto", "media", "explicit", 3.4, False)
check("none" in pet and "NO AUDIO" in pet, pet)


def J(pv, ne="", pa="", na="", accion="x"):
    return json.dumps({"accion_vista": accion, "prompt_video": pv, "negative_extra": ne,
                       "prompt_audio": pa, "negative_audio": na, "razonamiento": "ok"})


PV = ("The heavy man on the right keeps thrusting his hips hard into the man lying on his back, a steady fast "
      "rhythm, his belly bouncing with each thrust, the man below moaning with his mouth open, his body rocking "
      "on the sofa.")


def run(replies, **over):
    fake = base_t.FakeClient(replies)
    rps.anthropic = types.SimpleNamespace(Anthropic=lambda api_key: fake)
    args = dict(movimiento="", perfil_video="wan22_i2v", camara="fija", intensidad="media", nsfw="explicit",
                duracion_s=3.4, con_audio=True, creatividad=0.7, seed=0, imagen=None,
                receta=json.dumps(receta), api_key="k")
    args.update(over)
    return rv.RafaPromptVideo().generar(**args), fake


out, fake = run([J(PV, "woman", "skin slapping, heavy breathing, male moans", "female voice")])
pv, nv, pa, na, raz, segs = out
check(json.loads(segs) == [pv], segs)
check(pv.endswith("No zoom.") or "static camera" in pv.lower(), "camara fija anadida: " + pv)
check("woman" in nv and rv.WAN_NEG_GRUPO not in nv, nv)  # 2 personajes -> grupo
check(pa.startswith("skin") and na.startswith("music") and na.count("female voice") == 1, na)
check("Sin imagen conectada" in raz and "No hay perfil video" in raz, raz)
sys_txt = fake.calls[0]["system"][0]["text"]
check("AUDIO MODEL" in sys_txt and "Wan 2.2" in sys_txt, "system por defecto")

# trigger nombrado -> aviso
out, _ = run([J("Alfa thrusts hard into Gamma, fast rhythm, belly bouncing, moaning, sofa rocking, fixed camera, "
                "bodies moving together, sweat on the skin, hands gripping the cushions.")])
check("trigger «Alfa»" in out[4], out[4])

# sin audio
out, _ = run([J(PV, "", "should be dropped", "x")], con_audio=False)
check(out[2] == "" and out[3] == "", "sin audio vacio")

# bloqueo: reintenta y luego falla
try:
    run([J("a young man " + PV), J("a young man " + PV)])
    check(False, "debia bloquear")
except RuntimeError as e:
    check("bloqueado" in str(e), str(e))
out, fake = run([J("a young man " + PV), J(PV)])
check(len(fake.calls) == 2 and "young" not in out[0], "reintento corrige")

# peticion con termino prohibido -> ni llama a la API
try:
    run([J(PV)], movimiento="que el chaval se mueva")
    check(False, "debia rechazar")
except ValueError:
    OK += 1

# perfiles de video/audio desde .md
os.makedirs(os.path.join(PERF, "video"), exist_ok=True)
os.makedirs(os.path.join(PERF, "audio"), exist_ok=True)
open(os.path.join(PERF, "video", "wan22_i2v.md"), "w").write(
    "---\nnombre: Wan perfil\nnegative: NEGBASE\n---\nREGLAS DEL PERFIL\n## Historial\n- nada\n")
open(os.path.join(PERF, "audio", "mmaudio.md"), "w").write("---\nnegative: music\n---\nAUDIO DEL PERFIL\n")
out, fake = run([J(PV, "woman", "moans", "music, speech")])
s = fake.calls[0]["system"][0]["text"]
check("REGLAS DEL PERFIL" in s and "Historial" not in s and "AUDIO DEL PERFIL" in s, s[:200])
check(out[1] == "NEGBASE, woman" and out[3] == "music, speech", out)
check(rv.opciones("video", "x") == ["wan22_i2v"], "opciones")

# imagen -> base64 en el mensaje
import numpy as np
img = np.zeros((1, 16, 16, 3), dtype="float32")
out, fake = run([J(PV)], imagen=img)
c = fake.calls[0]["messages"][0]["content"]
check(c[0]["type"] == "image" and c[1]["type"] == "text", "imagen en el mensaje")

# segmentos (video largo)
def JS(segs):
    return json.dumps({"accion_vista": "x", "prompt_video": segs[0], "negative_extra": "", "prompt_audio": "moans",
                       "negative_audio": "", "segmentos": segs, "razonamiento": "ok"})
rec_prev = dict(receta, video={"segmentos_previos": ["seg A", "seg B"]})
out, fake = run([JS([PV, PV + " faster", PV + " climax"])], segmentos=3, receta=json.dumps(rec_prev))
check(len(json.loads(out[5])) == 3, out[5])
s0 = fake.calls[0]["system"][0]["text"]; m0 = fake.calls[0]["messages"][0]["content"][-1]["text"]
check("LONG VIDEO" in s0 and "3 segments" in m0 and "1. seg A" in m0, m0)
out, _ = run([JS([PV, PV])], segmentos=3)
check("Pedidos 3 segmentos, llegaron 2" in out[4], out[4])
out, fake = run([J(PV)])
check("LONG VIDEO" not in fake.calls[0]["system"][0]["text"], "sin segmentos")

# Prompt Studio registra la receta al generar
before = sum(1 for _ in open(REG))
base_t.run_node([base_t.J("[P1] lying on a bed.")])
lines = open(REG).read().strip().splitlines()
check(len(lines) == before + 1 and json.loads(lines[-1])["nodo"] == "RafaPromptStudio", "registro Studio")

print(f"OK {OK}")
