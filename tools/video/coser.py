# -*- coding: utf-8 -*-
"""Cose los tramos <tag>_t*.mp4 quitando los N primeros fotogramas de cada tramo a partir del 2.º
(encadenado por ultimo fotograma: N=1, porque el primer fotograma repite el ultimo del anterior) y le pone
audio con MMAudio sobre el video entero, con el prompt de audio del JSON de prompts.

  python3 coser.py <tag> <quitar> prompts.json [--fps 24] [--carpeta video_pruebas_20261108]
Imprime el salto en cada costura frente al movimiento tipico entre fotogramas (RGB, 0-255).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("tag")
ap.add_argument("quitar", type=int)
ap.add_argument("prompts_json")
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--carpeta", default="video_pruebas_20261108")
ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
D = os.path.join(lib.OUT, a.carpeta)
fs = sorted(f for f in os.listdir(D) if f.startswith(a.tag + "_t") and f.endswith(".mp4"))


def rgb(f):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "json", f], capture_output=True, text=True).stdout)["streams"][0]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, s["height"], s["width"], 3), s["width"], s["height"]


parts, saltos, W, H = [], [], 0, 0
for i, f in enumerate(fs):
    v, W, H = rgb(os.path.join(D, f))
    if i:
        saltos.append(round(float(np.abs(v[a.quitar].astype(float) - parts[-1][-1].astype(float)).mean()), 1))
        v = v[a.quitar:]
    parts.append(v)
v = np.concatenate(parts)
dif = np.abs(np.diff(v.astype(np.int16), axis=0)).mean(axis=(1, 2, 3))
mudo = os.path.join(D, "%s_cosido_mudo.mp4" % a.tag)
p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                      "-r", str(a.fps), "-i", "-", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", mudo],
                     stdin=subprocess.PIPE)
p.stdin.write(v.tobytes())
p.stdin.close()
p.wait()
print("cosido", os.path.basename(mudo), len(fs), "tramos", len(v), "fotogramas", round(len(v) / a.fps, 2), "s",
      "| salto en costuras", saltos, "| mov. tipico", round(float(np.median(dif)), 1), flush=True)

P = json.load(open(a.prompts_json))
name = os.path.basename(mudo)
shutil.copy2(mudo, os.path.join(lib.INPUT, name))
g = {"1": {"class_type": "LoadVideo", "inputs": {"file": name}},
     "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
     "3": {"class_type": "MMAudioModelLoader", "inputs": {"mmaudio_model": "mmaudio_large_44k_nsfw_fp16.safetensors",
                                                          "base_precision": "fp16"}},
     "4": {"class_type": "MMAudioFeatureUtilsLoader", "inputs": {
         "vae_model": "mmaudio_vae_44k_fp16.safetensors", "synchformer_model": "mmaudio_synchformer_fp16.safetensors",
         "clip_model": "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors", "mode": "44k", "precision": "fp16"}},
     "5": {"class_type": "MMAudioSampler", "inputs": {
         "mmaudio_model": ["3", 0], "feature_utils": ["4", 0], "images": ["2", 0], "duration": round(len(v) / a.fps, 3),
         "steps": 25, "cfg": 4.5, "seed": a.seed, "prompt": P["prompt_audio"], "negative_prompt": P["negative_audio"],
         "mask_away_clip": False, "force_offload": True}},
     "6": {"class_type": "CreateVideo", "inputs": {"images": ["2", 0], "fps": ["2", 2], "audio": ["5", 0]}},
     "7": {"class_type": "SaveVideo", "inputs": {"video": ["6", 0], "format": "mp4", "codec": "h264",
                                                 "filename_prefix": "%s/%s_cosido" % (a.carpeta, a.tag)}}}
pid, h, seg = lib.encolar_y_esperar(g)
print("audio", h.get("status", {}).get("status_str"), "%.0f s" % seg, flush=True)
