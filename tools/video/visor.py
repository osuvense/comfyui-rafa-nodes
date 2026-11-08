# -*- coding: utf-8 -*-
"""Visor HTML para que Rafa juzgue los videos (preferencia del 04/11): una tarjeta por pregunta, videos a ciegas
(A/B/C barajados en cada tarjeta, con la clave dentro del resultado), opciones, comentario y «Copiar resultado».
Se escribe en la carpeta de las pruebas, que se espeja al ICY con los videos (rutas relativas).

  python3 visor.py tarjetas.json --carpeta video_pruebas_20261108 --nombre visor.html
tarjetas.json: [{"id", "titulo", "mirar", "opciones": [...], "ciegas": true,
                 "videos": [{"id", "patron": "<glob dentro de la carpeta>", "prompt": "opcional"}]}]
"""
import argparse
import glob
import html
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("tarjetas")
ap.add_argument("--carpeta", default="video_pruebas_20261108")
ap.add_argument("--nombre", default="visor.html")
ap.add_argument("--semilla", type=int, default=20261108)
a = ap.parse_args()
D = os.path.join(lib.OUT, a.carpeta)
cards = json.load(open(a.tarjetas))
random.seed(a.semilla)
secs, faltan = [], []
for ci, c in enumerate(cards):
    vids = []
    for v in c["videos"]:
        fs = sorted(glob.glob(os.path.join(D, v["patron"])))
        if not fs:
            faltan.append(v["patron"])
            continue
        vids.append(dict(v, file=os.path.basename(fs[-1])))
    if c.get("ciegas", True):
        random.shuffle(vids)
    clave, cols = {}, []
    for i, v in enumerate(vids):
        L = "ABCDEFGH"[i]
        clave[L] = v["id"]
        pr = ('<details><summary>prompt</summary><p>%s</p></details>' % html.escape(v["prompt"])) if v.get("prompt") else ""
        cols.append('<div class="v"><div class="l">%s</div><video src="%s" controls loop preload="metadata"></video>%s</div>'
                    % (L, html.escape(v["file"]), pr))
    ops = "".join('<label><input type="radio" name="c%d" value="%s"> %s</label>' % (ci, html.escape(o), html.escape(o))
                  for o in c.get("opciones", []))
    secs.append('<section data-clave="%s" data-id="%s"><h2>%d. %s</h2><p class="m"><b>Qué mirar:</b> %s</p>'
                '<div class="g">%s</div><div class="o">%s</div><textarea placeholder="Comentario (opcional)"></textarea></section>'
                % (html.escape(json.dumps(clave)), html.escape(c["id"]), ci + 1, html.escape(c["titulo"]),
                   html.escape(c["mirar"]), "".join(cols), ops))
page = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pruebas de vídeo</title><style>body{font-family:-apple-system,system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:16px}
section{background:#1c1c1c;border-radius:10px;padding:14px;margin:0 0 18px}h2{margin:0 0 6px;font-size:18px}.m{color:#bbb}
.g{display:flex;gap:10px;flex-wrap:wrap}.v{flex:1 1 300px}.v video{width:100%;background:#000;border-radius:6px}.l{font-weight:700;font-size:20px;margin:4px 0}
.o label{display:inline-block;margin:6px 12px 0 0}textarea{width:100%;margin-top:8px;min-height:44px;background:#222;color:#eee;border:1px solid #444;border-radius:6px}
details p{font-size:12px;color:#aaa}button{font-size:16px;padding:10px 16px;border-radius:8px;border:0;background:#3a7;color:#fff;position:sticky;bottom:10px}</style></head><body>
<h1>Pruebas de vídeo — """ + html.escape(a.carpeta + " / " + a.nombre) + """</h1><p>Las letras están barajadas en cada tarjeta. Contesta y pulsa «Copiar resultado»; pégamelo en el chat.</p>
""" + "\n".join(secs) + """<button onclick="copiar()">Copiar resultado</button><script>
function copiar(){let r=[];document.querySelectorAll('section').forEach(s=>{const k=JSON.parse(s.dataset.clave);const sel=s.querySelector('input:checked');
r.push(s.dataset.id+': '+(sel?sel.value:'-')+' | '+(s.querySelector('textarea').value||'')+' | clave '+Object.entries(k).map(([a,b])=>a+'='+b).join(' '))});
const t=r.join('\\n');navigator.clipboard.writeText(t).then(()=>alert('Copiado'),()=>{prompt('Copia esto:',t)});}</script></body></html>"""
open(os.path.join(D, a.nombre), "w").write(page)
print("visor", os.path.join(D, a.nombre), len(cards), "tarjetas", "| faltan:", faltan or "ninguno")
