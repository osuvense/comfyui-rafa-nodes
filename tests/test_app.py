# -*- coding: utf-8 -*-
"""Tests de la app (sin red ni GPU): galeria, receta, preparar video (Claude falso) y grafo de animar.
Uso: python3 tests/test_app.py"""
import json, os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import test_prompt_studio as base_t
base_t.make_dir()
D = tempfile.mkdtemp(); os.environ["RAFA_SALIDAS"] = D; os.environ["RAFA_RECETAS_DIR"] = tempfile.mkdtemp()
from PIL import Image, PngImagePlugin
import rafa_prompt_studio as rps
os.makedirs(os.path.join(D, "krea"), exist_ok=True)
meta = PngImagePlugin.PngInfo()
meta.add_text("prompt", json.dumps({"3": {"class_type": "RafaPromptStudio", "inputs": {"escena": "Alfa en un sofa", "personaje_1": "alfa", "seed": 1}}}))
Image.new("RGB", (64, 96), (90, 60, 40)).save(os.path.join(D, "krea", "a.png"), pnginfo=meta)
os.makedirs(os.path.join(D, "_diag")); Image.new("RGB", (8, 8)).save(os.path.join(D, "_diag", "x.png"))
from app import servidor as S
OK = 0
def check(c, m):
    global OK
    assert c, m; OK += 1
g = S.galeria()
check([x["rel"] for x in g] == ["krea/a.png"], g)
try:
    S.ruta_segura("../etc/passwd"); check(False, "debia fallar")
except ValueError:
    OK += 1
r = S.receta("krea/a.png"); check(r["escena"] == "Alfa en un sofa" and r["personajes"] == ["alfa"], r)
PV = "The heavy man on the sofa rocks his hips in a steady fast rhythm, belly bouncing, moaning with his mouth open, his body pressing into the cushions, sweat on his skin."
fake = base_t.FakeClient([json.dumps({"accion_vista": "x", "personas": 1, "prompt_video": PV, "negative_extra": "",
                                      "prompt_audio": "male moans, sofa creaking", "negative_audio": "", "razonamiento": "ok"})])
rps.anthropic = types.SimpleNamespace(Anthropic=lambda api_key: fake); os.environ["ANTHROPIC_API_KEY"] = "k"
p = S.preparar_video("krea/a.png")
check(p["prompt_video"].startswith("The heavy man") and p["segmentos"] and p["receta"]["origen"].startswith("studio"), p)
check(fake.calls[0]["messages"][0]["content"][0]["type"] == "image", "la imagen va a Claude")
gr = S.grafo_animar("app_a.png", p, 7, 832, 480)
check(gr["8"]["inputs"]["image"] == "app_a.png" and gr["100"]["inputs"]["text"] == p["prompt_video"], "inyeccion")
check(gr["101"]["inputs"]["width"] == 832 and gr["102"]["inputs"]["seed"] == 7, "tamano y seed")
check(not any(n["class_type"].startswith("Rafa") for n in gr.values()), "sin nodos de Claude en el grafo del pod")
bad = [(k, i) for k, n in gr.items() for i, v in n["inputs"].items() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] not in gr]
check(not bad, bad)
from fastapi.testclient import TestClient
c = TestClient(S.app)
check(c.get("/").status_code == 200 and "Preparar vídeo" in c.get("/").text, "pagina")
check(c.get("/api/galeria").json()[0]["rel"] == "krea/a.png", "api galeria")
check(c.get("/api/imagen", params={"rel": "krea/a.png", "lado": 32}).headers["content-type"] == "image/jpeg", "miniatura")
check(c.get("/api/config").json()["comfy"] is None, "sin pod")
check(c.post("/api/animar", json={"rel": "krea/a.png", "prep": p}).status_code == 400, "animar sin pod = 400")
print(f"OK {OK}")
