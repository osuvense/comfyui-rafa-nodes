# -*- coding: utf-8 -*-
"""Saca la receta y los prompts de video/audio de una imagen con los nodos Cargar imagen con receta +
Prompt de video (sin GPU: solo llama a Claude). Guarda un JSON que leen largo.py y clip.py.

  python3 prompts.py <imagen> --out p.json [--mov "texto"] [--seg 3] [--int intensa] [--cam fija] [--seed 0]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("imagen")
ap.add_argument("--out", required=True)
ap.add_argument("--mov", default="")
ap.add_argument("--seg", type=int, default=1)
ap.add_argument("--int", dest="intensidad", default="intensa")
ap.add_argument("--cam", default="fija")
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()

nombre = lib.a_input(a.imagen)
N = ["prompt_video", "negative_video", "prompt_audio", "negative_audio", "razonamiento", "segmentos"]
g = {"1": {"class_type": "RafaCargarReceta", "inputs": {"image": nombre}},
     "2": {"class_type": "RafaPromptVideo", "inputs": {
         "movimiento": a.mov, "perfil_video": "wan22_i2v", "camara": a.cam, "intensidad": a.intensidad,
         "nsfw": "explicit", "duracion_s": 3.4, "con_audio": True, "segmentos": a.seg, "creatividad": 0.7,
         "seed": a.seed, "imagen": ["1", 0], "receta": ["1", 1], "perfil_audio": "mmaudio", "api_key": "",
         "modelo_claude": "claude-sonnet-4-6", "extra": ""}},
     "20": {"class_type": "ShowText|pysssss", "inputs": {"text": ["1", 1]}}}
for i in range(len(N)):
    g["1%d" % i] = {"class_type": "ShowText|pysssss", "inputs": {"text": ["2", i]}}
pid, h, seg = lib.encolar_y_esperar(g, 2)
if h.get("status", {}).get("status_str") != "success":
    sys.exit(json.dumps(h.get("status"))[:3000])
vals = lib.textos_showtext(h["outputs"], ["1%d" % i for i in range(len(N))] + ["20"])
res = dict(zip(N, vals[:-1]))
res["receta"] = json.loads(vals[-1] or "{}")
res["imagen"] = os.path.abspath(a.imagen)
res["args"] = vars(a)
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
print("OK", a.out, "| origen", res["receta"].get("origen"), "| %.0f s" % seg)
for av in res["razonamiento"].split("----")[0].splitlines():
    if av.strip().startswith("-"):
        print("  aviso", av.strip())
