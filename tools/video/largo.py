# -*- coding: utf-8 -*-
"""Video largo con Rapid AIO V10 encadenando cada tramo desde el ULTIMO FOTOGRAMA del anterior (lo que eligio
Rafa el 07/11; SVI y Remix descartados). Variables para atacar la «cara que aparece de la nada» al final:

  --clip original|ultimo  CLIP vision de la imagen original en todos los tramos (ancla de identidad y escena)
                          o del ultimo fotograma (como el 07/11).
  --frames 81|65|49       largo de cada tramo (tramos mas cortos = menos deriva por tramo).
  --tramos N              numero de tramos (por defecto, los del JSON de prompts; si hay menos prompts, se repite el ultimo).
  --refinar 0.25          antes de reusar el ultimo fotograma, img2img suave con Krea 2 (SNOFS Turbo) + LoRA de los
                          personajes de la receta (identidad). 0 = no.
  --nag                   NAG con el negative del JSON (+ --negextra).

Mismos ajustes que la prueba del 31/10: 480x832, 4 pasos, CFG 1, euler_ancestral/beta, shift 8, 24 fps; seed+i por tramo.
Salidas: video_pruebas_<fecha>/<tag>_t<i>.mp4 (cada tramo). Coser y audio: coser.py.

  python3 largo.py prompts.json --tag X [--clip original] [--frames 65] [--refinar 0.25]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("prompts_json")
ap.add_argument("--tag", required=True)
ap.add_argument("--carpeta", default="video_pruebas_20261108")
ap.add_argument("--clip", default="ultimo", choices=["ultimo", "original"])
ap.add_argument("--frames", type=int, default=81)
ap.add_argument("--tramos", type=int, default=0)
ap.add_argument("--refinar", type=float, default=0.0)
ap.add_argument("--nag", action="store_true")
ap.add_argument("--negextra", default="")
ap.add_argument("--w", type=int, default=480)
ap.add_argument("--h", type=int, default=832)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--imagen", default="", help="si el JSON de prompts no trae la imagen")
a = ap.parse_args()
LOG = os.path.join(lib.TRABAJO, "largo.log")

P = json.load(open(a.prompts_json))
segs = json.loads(P["segmentos"]) if isinstance(P["segmentos"], str) else P["segmentos"]
n = a.tramos or len(segs)
segs = [segs[min(i, len(segs) - 1)] for i in range(n)]
NEG = P["negative_video"] + (", " + a.negextra if a.negextra else "")
nombre = lib.a_input(a.imagen or P["imagen"])

g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": lib.V10}},
     "7": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "clip_vision_h.safetensors"}},
     "8": {"class_type": "LoadImage", "inputs": {"image": nombre}},
     "10": {"class_type": "ImageScale", "inputs": {"image": ["8", 0], "upscale_method": "lanczos",
                                                   "width": a.w, "height": a.h, "crop": "center"}},
     "12": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
     "13": {"class_type": "CLIPVisionEncode", "inputs": {"crop": "center", "clip_vision": ["7", 0], "image": ["10", 0]}}}
model = ["1", 0]
if a.nag:
    g["3"] = {"class_type": "WanVideoNAG", "inputs": {"model": model, "conditioning": ["12", 0], "nag_scale": 11.0,
                                                      "nag_alpha": 0.25, "nag_tau": 2.5}}
    model = ["3", 0]
g["4"] = {"class_type": "ModelSamplingSD3", "inputs": {"shift": 8.0, "model": model}}

if a.refinar > 0:
    # Krea 2 para limpiar el ultimo fotograma (mismos modelos que el WF de Reparto, freefuse/wf_freefuse_reparto.json)
    sys.path.insert(0, "/workspace/apps/comfy/custom_nodes/comfyui-rafa-nodes")
    os.environ.setdefault("RAFA_PERFILES_DIR", "/workspace/perfiles_prompt")
    import rafa_prompt_studio as rps
    pers = (P.get("receta") or {}).get("personajes") or []
    loras = [l for l in (P.get("receta") or {}).get("loras") or [] if str(l.get("lora", "")).startswith("Krea2/")
             and (l.get("fuerza") or 0) > 0]
    aperturas = []
    for c in pers:
        try:
            aperturas.append(rps.apertura(rps.load_personaje(c)))
        except Exception:
            pass
    texto = ("; ".join(aperturas) + ". " if aperturas else "") + "Sharp phone photograph, natural skin texture."
    g.update({"60": {"class_type": "UNETLoader", "inputs": {"unet_name": "snofsSexNudesAndOther_krea2TurboV14.safetensors",
                                                           "weight_dtype": "default"}},
              "61": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
                                                           "type": "krea2", "device": "default"}},
              "62": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
              "64": {"class_type": "CLIPTextEncode", "inputs": {"text": texto, "clip": ["61", 0]}},
              "65": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["64", 0]}}})
    km = ["60", 0]
    for j, l in enumerate(loras):
        g["7%d" % j] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": km, "lora_name": l["lora"],
                                                                        "strength_model": l.get("fuerza") or 1.0}}
        km = ["7%d" % j, 0]
    lib.log(LOG, a.tag, "refinar con Krea:", texto, "| LoRAs", [l["lora"] for l in loras])

prev_img = ["10", 0]
for i, txt in enumerate(segs):
    b = 100 + i * 20
    g[str(b)] = {"class_type": "CLIPTextEncode", "inputs": {"text": txt, "clip": ["1", 1]}}
    clip_out = ["13", 0] if a.clip == "original" else [str(b + 8), 0]
    if a.clip == "ultimo":
        g[str(b + 8)] = {"class_type": "CLIPVisionEncode", "inputs": {"crop": "center", "clip_vision": ["7", 0],
                                                                      "image": prev_img}}
    g[str(b + 1)] = {"class_type": "WanImageToVideo", "inputs": {
        "width": a.w, "height": a.h, "length": a.frames, "batch_size": 1, "positive": [str(b), 0],
        "negative": ["12", 0], "vae": ["1", 2], "clip_vision_output": clip_out, "start_image": prev_img}}
    g[str(b + 2)] = {"class_type": "KSampler", "inputs": {
        "seed": a.seed + i, "steps": 4, "cfg": 1.0, "sampler_name": "euler_ancestral", "scheduler": "beta",
        "denoise": 1.0, "model": ["4", 0], "positive": [str(b + 1), 0], "negative": [str(b + 1), 1],
        "latent_image": [str(b + 1), 2]}}
    g[str(b + 4)] = {"class_type": "VAEDecode", "inputs": {"samples": [str(b + 2), 0], "vae": ["1", 2]}}
    g[str(b + 5)] = {"class_type": "CreateVideo", "inputs": {"images": [str(b + 4), 0], "fps": 24.0}}
    g[str(b + 6)] = {"class_type": "SaveVideo", "inputs": {"video": [str(b + 5), 0], "format": "mp4", "codec": "h264",
                                                           "filename_prefix": "%s/%s_t%d" % (a.carpeta, a.tag, i + 1)}}
    g[str(b + 7)] = {"class_type": "ImageFromBatch", "inputs": {"image": [str(b + 4), 0], "batch_index": a.frames - 1,
                                                               "length": 1}}
    prev_img = [str(b + 7), 0]
    if a.refinar > 0 and i < len(segs) - 1:
        g[str(b + 10)] = {"class_type": "VAEEncode", "inputs": {"pixels": prev_img, "vae": ["62", 0]}}
        g[str(b + 11)] = {"class_type": "KSampler", "inputs": {
            "seed": a.seed + i, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
            "denoise": a.refinar, "model": km, "positive": ["64", 0], "negative": ["65", 0],
            "latent_image": [str(b + 10), 0]}}
        g[str(b + 12)] = {"class_type": "VAEDecode", "inputs": {"samples": [str(b + 11), 0], "vae": ["62", 0]}}
        g[str(b + 13)] = {"class_type": "ImageScale", "inputs": {"image": [str(b + 12), 0], "upscale_method": "lanczos",
                                                                 "width": a.w, "height": a.h, "crop": "center"}}
        g[str(b + 14)] = {"class_type": "SaveImage", "inputs": {"images": [str(b + 13), 0],
                                                                "filename_prefix": "%s/%s_refinado_t%d" % (a.carpeta, a.tag, i + 1)}}
        prev_img = [str(b + 13), 0]

lib.log(LOG, a.tag, "encolado", vars(a))
pid, h, seg = lib.encolar_y_esperar(g)
st = h.get("status", {}).get("status_str")
lib.log(LOG, a.tag, st, "%.0f s" % seg)
if st != "success":
    lib.log(LOG, json.dumps(h.get("status"))[:3000])
    sys.exit(1)
json.dump({"tag": a.tag, "args": vars(a), "segundos": round(seg), "segmentos": segs, "negative": NEG},
          open(os.path.join(lib.TRABAJO, "largo_%s.json" % a.tag), "w"), ensure_ascii=False, indent=1)
