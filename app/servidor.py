# -*- coding: utf-8 -*-
"""App de Rafa — esqueleto (fase 2 de video/app_diseno.md): servidor en el Mac, usada desde el iPad (red de casa o
Tailscale). NO la carga ComfyUI.

Hoy hace:
  - Galeria de lo ultimo generado (carpeta de salidas del espejo del ICY).
  - Abrir una imagen: su receta (rafa_receta) - escena, prompt, personajes.
  - «Preparar video» SIN GPU: el prompt de video y el de audio con la misma logica del nodo Prompt de video
    (Claude mira la imagen y la receta). Uno o varios tramos.
  - «Animar» contra un ComfyUI (el pod): sube la imagen y lanza el WF de animar con el prompt ya escrito
    (inyeccion como el bot v2; el nodo de Claude no va dentro del grafo). Estado del trabajo.
Lo que se actualiza solo: perfiles (lee perfiles_prompt/ del Mac), nodos (importa el repo; boton «actualizar» =
git pull + recarga), workflows (plantillas en app/plantillas/).

Arranque:  RAFA_SALIDAS="/Volumes/ICY BOX/ComfyUI/Outputs" RAFA_PERFILES_DIR=".../perfiles_prompt" \
           ANTHROPIC_API_KEY=... python3 -m uvicorn app.servidor:app --host 0.0.0.0 --port 8765
"""
import base64
import importlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import rafa_prompt_studio as rps  # noqa: E402
import rafa_receta as rr  # noqa: E402
import rafa_video as rv  # noqa: E402

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse, Response
    from pydantic import BaseModel
except Exception:  # los tests de la logica no necesitan FastAPI
    FastAPI = None

SALIDAS = os.getenv("RAFA_SALIDAS", "/Volumes/ICY BOX/ComfyUI/Outputs")
EXT_IMG = (".png", ".jpg", ".jpeg", ".webp")
ESTADO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_estado.json")


# ============================================================
# Logica (sin FastAPI; testeable)
# ============================================================

def ruta_segura(rel: str) -> str:
    """Ruta dentro de SALIDAS (sin salirse con ..)."""
    p = os.path.realpath(os.path.join(SALIDAS, rel))
    if not p.startswith(os.path.realpath(SALIDAS) + os.sep):
        raise ValueError("Ruta fuera de la carpeta de salidas")
    return p


def galeria(limite: int = 60, sub: str = "") -> List[Dict[str, Any]]:
    base = ruta_segura(sub) if sub else SALIDAS
    fs = []
    for dp, _, ns in os.walk(base):
        if "/_" in dp.replace(base, ""):
            continue
        for n in ns:
            if n.lower().endswith(EXT_IMG) and not n.startswith("."):
                p = os.path.join(dp, n)
                try:
                    fs.append((os.path.getmtime(p), p))
                except OSError:
                    pass
    fs.sort(reverse=True)
    return [{"rel": os.path.relpath(p, SALIDAS), "mtime": int(t)} for t, p in fs[:limite]]


def receta(rel: str) -> Dict[str, Any]:
    return rr.receta_de_png(ruta_segura(rel))


def imagen_np(rel: str, lado: int = 1024):
    import numpy as np
    from PIL import Image
    with Image.open(ruta_segura(rel)) as im:
        im = im.convert("RGB")
        im.thumbnail((lado, lado))
        return (np.asarray(im).astype("float32") / 255.0)[None, ...]


def preparar_video(rel: str, movimiento: str = "", segmentos: int = 1, intensidad: str = "intensa",
                   camara: str = "fija", con_audio: bool = True, seed: int = 0) -> Dict[str, Any]:
    """Prompt de video y de audio con el mismo codigo del nodo (Claude ve la imagen). Sin GPU."""
    rec = receta(rel)
    out = rv.RafaPromptVideo().generar(
        movimiento=movimiento, perfil_video="wan22_i2v", camara=camara, intensidad=intensidad, nsfw="explicit",
        duracion_s=3.4, con_audio=con_audio, creatividad=0.7, seed=seed, imagen=imagen_np(rel),
        receta=json.dumps(rec, ensure_ascii=False), segmentos=segmentos)
    claves = ["prompt_video", "negative_video", "prompt_audio", "negative_audio", "razonamiento", "segmentos"]
    res = dict(zip(claves, out))
    res["segmentos"] = json.loads(res["segmentos"] or "[]")
    res["receta"] = rec
    return res


# ---------- ComfyUI (el pod) ----------

def comfy_url() -> str:
    return os.getenv("RAFA_COMFY_URL", "").rstrip("/")


def _req(url: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def subir_imagen(rel: str) -> str:
    """POST /upload/image (multipart) al ComfyUI; devuelve el nombre en su input/."""
    p = ruta_segura(rel)
    b = "----rafa" + str(int(time.time() * 1000))
    nombre = "app_" + os.path.basename(p)
    with open(p, "rb") as fh:
        datos = fh.read()
    cuerpo = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{nombre}\"\r\n"
              f"Content-Type: image/png\r\n\r\n").encode() + datos + f"\r\n--{b}\r\nContent-Disposition: form-data; " \
             f"name=\"overwrite\"\r\n\r\ntrue\r\n--{b}--\r\n".encode()
    r = _req(comfy_url() + "/upload/image", cuerpo, {"Content-Type": f"multipart/form-data; boundary={b}"})
    return r["name"]


def plantilla(nombre: str) -> Dict[str, Any]:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantillas", nombre + ".json")) as fh:
        return json.load(fh)


def grafo_animar(imagen_input: str, prep: Dict[str, Any], seed: int = 42, w: int = 480, h: int = 832) -> Dict[str, Any]:
    """WF de animar SIN el nodo de Claude: el prompt ya viene escrito (como el bot v2)."""
    g = plantilla("animar")
    g["8"]["inputs"]["image"] = imagen_input
    g["10"]["inputs"].update({"width": w, "height": h})
    g["101"]["inputs"].update({"width": w, "height": h})
    g["100"]["inputs"]["text"] = prep["prompt_video"]
    g["12"]["inputs"]["text"] = prep["negative_video"]
    g["92"]["inputs"].update({"prompt": prep["prompt_audio"], "negative_prompt": prep["negative_audio"], "seed": seed})
    g["102"]["inputs"]["seed"] = seed
    return g


def animar(rel: str, prep: Dict[str, Any], seed: int = 42) -> Dict[str, Any]:
    if not comfy_url():
        raise RuntimeError("Falta RAFA_COMFY_URL (la URL del ComfyUI del pod)")
    nombre = subir_imagen(rel)
    w, h = (480, 832)
    try:
        from PIL import Image
        with Image.open(ruta_segura(rel)) as im:
            if im.width > im.height:
                w, h = (832, 480)
    except Exception:
        pass
    g = grafo_animar(nombre, prep, seed, w, h)
    r = _req(comfy_url() + "/prompt", json.dumps({"prompt": g}).encode(), {"Content-Type": "application/json"})
    pid = r["prompt_id"]
    estado = _leer_estado()
    estado[pid] = {"tipo": "animar", "imagen": rel, "prep": prep, "ts": time.time(), "padre": rel}
    _guardar_estado(estado)
    return {"prompt_id": pid}


def trabajo(pid: str) -> Dict[str, Any]:
    h = _req(comfy_url() + "/history/" + urllib.parse.quote(pid))
    if pid not in h:
        q = _req(comfy_url() + "/queue")
        enc = any(x[1] == pid for x in q.get("queue_running", []))
        return {"estado": "en curso" if enc else "en cola"}
    st = h[pid].get("status", {}).get("status_str")
    vids = [x for o in h[pid]["outputs"].values() for x in (o.get("images") or o.get("videos") or [])
            if str(x.get("filename", "")).endswith(".mp4")]
    return {"estado": st, "videos": vids}


def _leer_estado() -> Dict[str, Any]:
    try:
        with open(ESTADO_PATH) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _guardar_estado(e: Dict[str, Any]) -> None:
    with open(ESTADO_PATH, "w") as fh:
        json.dump(e, fh, ensure_ascii=False, indent=1)


def actualizar_nodos() -> str:
    """git pull del repo y recarga de los modulos (perfiles: se leen en cada llamada, no hace falta)."""
    out = subprocess.run(["git", "-C", RAIZ, "pull", "--ff-only"], capture_output=True, text=True)
    for m in (rps, rr, rv):
        importlib.reload(m)
    return (out.stdout + out.stderr).strip()


# ============================================================
# API
# ============================================================

if FastAPI is not None:
    app = FastAPI(title="App de Rafa")

    class PrepIn(BaseModel):
        rel: str
        movimiento: str = ""
        segmentos: int = 1
        intensidad: str = "intensa"
        camara: str = "fija"
        con_audio: bool = True
        seed: int = 0

    class AnimarIn(BaseModel):
        rel: str
        prep: Dict[str, Any]
        seed: int = 42

    @app.get("/", response_class=HTMLResponse)
    def inicio():
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html"), encoding="utf-8") as fh:
            return fh.read()

    @app.get("/api/galeria")
    def api_galeria(limite: int = 60, sub: str = ""):
        return galeria(limite, sub)

    @app.get("/api/imagen")
    def api_imagen(rel: str, lado: int = 0):
        p = ruta_segura(rel)
        if not lado:
            return FileResponse(p)
        from PIL import Image
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((lado, lado))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
        return Response(buf.getvalue(), media_type="image/jpeg")

    @app.get("/api/receta")
    def api_receta(rel: str):
        return receta(rel)

    @app.post("/api/preparar_video")
    def api_preparar(x: PrepIn):
        try:
            return preparar_video(x.rel, x.movimiento, x.segmentos, x.intensidad, x.camara, x.con_audio, x.seed)
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.post("/api/animar")
    def api_animar(x: AnimarIn):
        try:
            return animar(x.rel, x.prep, x.seed)
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.get("/api/trabajo")
    def api_trabajo(pid: str):
        return trabajo(pid)

    @app.get("/api/video")
    def api_video(filename: str, subfolder: str = ""):
        if not comfy_url():
            raise HTTPException(400, "Sin RAFA_COMFY_URL")
        q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
        with urllib.request.urlopen(comfy_url() + "/view?" + q, timeout=120) as r:
            return Response(r.read(), media_type="video/mp4")

    @app.post("/api/actualizar")
    def api_actualizar():
        return {"salida": actualizar_nodos()}

    @app.get("/api/config")
    def api_config():
        return {"salidas": SALIDAS, "comfy": comfy_url() or None, "perfiles": rps.perfiles_dir(),
                "personajes": rps.personaje_options()}
