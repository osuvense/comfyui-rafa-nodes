# -*- coding: utf-8 -*-
"""Ayudas comunes de las pruebas de video por la API de ComfyUI (pod LoraPilot).

Rutas del pod (comprobadas el 07/11/2026): ComfyUI en /opt/pilot/repos/ComfyUI, puerto 5555; su input/ NO esta en el
volumen; las salidas van a /workspace/outputs/comfy (espejo al ICY). Nada de esto lo importa ComfyUI.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

U = os.getenv("COMFY_URL", "http://127.0.0.1:5555")
INPUT = os.getenv("COMFY_INPUT", "/opt/pilot/repos/ComfyUI/input")
OUT = os.getenv("COMFY_OUT", "/workspace/outputs/comfy")
TRABAJO = os.getenv("VIDEO_TRABAJO", "/workspace/_claude/video")
V10 = "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors"


def log(path, *a):
    s = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(s + "\n")


def get(p):
    with urllib.request.urlopen(U + p, timeout=60) as r:
        return json.loads(r.read())


def post(p, d):
    req = urllib.request.Request(U + p, data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit("HTTP %s: %s" % (e.code, e.read().decode()[:3000]))


def encolar_y_esperar(g, cada=5):
    pid = post("/prompt", {"prompt": g})["prompt_id"]
    t0 = time.time()
    while True:
        h = get("/history/" + pid)
        if pid in h:
            return pid, h[pid], time.time() - t0
        time.sleep(cada)


def a_input(ruta, prefijo="receta_"):
    """Copia un archivo a input/ de ComfyUI (si no esta) y devuelve el nombre."""
    nombre = prefijo + os.path.basename(ruta)
    dst = os.path.join(INPUT, nombre)
    if not os.path.exists(dst):
        shutil.copy2(ruta, dst)
    return nombre


def textos_showtext(outputs, ids):
    res = []
    for k in ids:
        t = (outputs.get(k) or {}).get("text") or [""]
        res.append(t[0] if isinstance(t, list) else t)
    return res


def ultimo(patron):
    fs = sorted(glob.glob(patron))
    return fs[-1] if fs else None


def frames_gray(f, w=240):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate", "-of", "json", f],
                                  capture_output=True, text=True).stdout)["streams"][0]
    import numpy as np
    h = int(round(s["height"] * w / s["width"] / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", "scale=%d:%d" % (w, h), "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32), s
