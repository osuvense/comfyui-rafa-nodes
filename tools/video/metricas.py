# -*- coding: utf-8 -*-
"""Señales tecnicas de los videos de una carpeta de pruebas (no son calidad: la calidad la juzga Rafa).
Por video: movimiento medio entre fotogramas (gris 240 px, 0-255), por tercios, y deriva final frente al inicio.
Por video cosido con tramos: deriva del ultimo fotograma de cada tramo frente al primero del video (cuanto se aleja
de la imagen de partida tramo a tramo; la «cara de la nada» deberia subirla en el ultimo tramo).

  python3 metricas.py [--carpeta video_pruebas_20261108]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--carpeta", default="video_pruebas_20261108")
a = ap.parse_args()
D = os.path.join(lib.OUT, a.carpeta)
out = {}
for f in sorted(os.listdir(D)):
    if not f.endswith(".mp4") or "_mudo" in f:
        continue
    v, s = lib.frames_gray(os.path.join(D, f))
    d = np.abs(np.diff(v, axis=0)).mean(axis=(1, 2))
    n = len(d)
    r = {"fotogramas": int(v.shape[0]), "fps": s["r_frame_rate"], "mov_media": round(float(d.mean()), 2),
         "mov_1er_tercio": round(float(d[: n // 3].mean()), 2), "mov_ultimo_tercio": round(float(d[2 * n // 3:].mean()), 2),
         "deriva_final": round(float(np.abs(v[-1] - v[0]).mean()), 2)}
    if "_cosido" in f:
        k = max(1, v.shape[0] // 8)
        r["deriva_por_octavos"] = [round(float(np.abs(v[min(j * k, v.shape[0] - 1)] - v[0]).mean()), 1) for j in range(1, 9)]
    out[f] = r
json.dump(out, open(os.path.join(D, "_metricas.json"), "w"), indent=1)
for k, v in out.items():
    print(k, v)
