# -*- coding: utf-8 -*-
"""Plantillas de la app a partir de los WF que genera tools/video/wf.py, quitando lo que corre en el Mac
(el nodo de Claude y los ShowText): la app escribe el prompt antes y lo inyecta (como el bot v2).
  python3 app/hacer_plantillas.py
"""
import json, os, subprocess, sys, tempfile
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = tempfile.mkdtemp()
subprocess.run([sys.executable, os.path.join(R, "tools/video/wf.py"), "--dest", d], check=True, capture_output=True)
g = json.load(open(os.path.join(d, "7 Animar con receta (API).json")))
for k in [k for k, n in g.items() if n["class_type"] in ("RafaPromptVideo", "ShowText|pysssss")]:
    del g[k]
g["8"] = {"class_type": "LoadImage", "inputs": {"image": "example.png"}, "_meta": {"title": "Imagen (la sube la app)"}}
g["100"]["inputs"]["text"] = ""
g["12"]["inputs"]["text"] = ""
g["92"]["inputs"].update({"prompt": "", "negative_prompt": ""})
rotos = [(k, i) for k, n in g.items() for i, v in n["inputs"].items() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] not in g]
assert not rotos, rotos
json.dump(g, open(os.path.join(R, "app/plantillas/animar.json"), "w"), ensure_ascii=False, indent=1)
print("ok animar.json", len(g), "nodos")
