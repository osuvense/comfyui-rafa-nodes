# -*- coding: utf-8 -*-
"""Genera los workflows definitivos de video en formato API (se cargan en ComfyUI arrastrando el JSON):

  7 Animar con receta (API).json : Cargar imagen con receta -> Prompt de video -> Rapid AIO V10 -> MMAudio -> mp4 con audio
  8 Video largo (API).json       : lo mismo en N tramos encadenados por el ultimo fotograma (Elegir tramo por tramo),
                                   cosidos quitando el primer fotograma de cada tramo, y audio sobre el total.

Decisiones de Rafa (07/11): V10, sin NAG, prompt y audio del nodo, video largo por ultimo fotograma.
Opciones abiertas tras las pruebas del 08/11: --clip original|ultimo y --frames.

  python3 wf.py --dest /workspace/apps/comfy/user/default/workflows [--tramos 3] [--clip original] [--frames 81]
"""
import argparse
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("--dest", default="/workspace/apps/comfy/user/default/workflows")
ap.add_argument("--tramos", type=int, default=3)
ap.add_argument("--clip", default="original", choices=["original", "ultimo"])
ap.add_argument("--frames", type=int, default=81)
ap.add_argument("--imagen", default="example.png")
a = ap.parse_args()
V10 = "wan2.2-i2v-rapid-aio-v10-nsfw.safetensors"


def T(g, nid, cls, titulo, **ins):
    g[str(nid)] = {"class_type": cls, "inputs": ins, "_meta": {"title": titulo}}


def base(g, segmentos):
    T(g, 1, "CheckpointLoaderSimple", "Modelo: Wan 2.2 Rapid AIO V10 NSFW", ckpt_name=V10)
    T(g, 4, "ModelSamplingSD3", "Shift 8", shift=8.0, model=["1", 0])
    T(g, 7, "CLIPVisionLoader", "CLIP vision H", clip_name="clip_vision_h.safetensors")
    T(g, 8, "RafaCargarReceta", "Imagen a animar (sube aquí la imagen generada: trae su receta)", image=a.imagen)
    T(g, 10, "ImageScale", "480×832 (cámbialo para horizontal)", image=["8", 0], upscale_method="lanczos",
      width=480, height=832, crop="center")
    T(g, 2, "RafaPromptVideo", "Prompt de vídeo: escribe aquí qué quieres que pase (vacío = sigue la acción)",
      movimiento="", perfil_video="wan22_i2v", camara="fija", intensidad="intensa", nsfw="explicit",
      duracion_s=round(a.frames / 24, 2), con_audio=True, segmentos=segmentos, creatividad=0.7, seed=0,
      imagen=["8", 0], receta=["8", 1], perfil_audio="mmaudio", api_key="", modelo_claude="claude-sonnet-4-6", extra="")
    T(g, 3, "ShowText|pysssss", "Razonamiento y avisos del prompt", text=["2", 4])
    T(g, 5, "ShowText|pysssss", "Prompt de vídeo", text=["2", 0])
    T(g, 6, "ShowText|pysssss", "Prompt de audio", text=["2", 2])
    T(g, 12, "CLIPTextEncode", "Negativo (a CFG 1 no actúa; sin NAG por decisión de Rafa)", text=["2", 1], clip=["1", 1])
    T(g, 13, "CLIPVisionEncode", "CLIP vision de la imagen original", crop="center", clip_vision=["7", 0], image=["10", 0])
    T(g, 20, "PrimitiveInt", "Seed del vídeo", value=42)


def tramo(g, b, i, texto, start, clip_out):
    T(g, b, "CLIPTextEncode", "Tramo %d: prompt" % i, text=texto, clip=["1", 1])
    T(g, b + 1, "WanImageToVideo", "Tramo %d" % i, width=480, height=832, length=a.frames, batch_size=1,
      positive=[str(b), 0], negative=["12", 0], vae=["1", 2], clip_vision_output=clip_out, start_image=start,
      )
    T(g, b + 2, "KSampler", "Tramo %d: 4 pasos, CFG 1" % i, seed=["20", 0], steps=4, cfg=1.0,
      sampler_name="euler_ancestral", scheduler="beta", denoise=1.0, model=["4", 0], positive=[str(b + 1), 0],
      negative=[str(b + 1), 1], latent_image=[str(b + 1), 2])
    T(g, b + 3, "VAEDecode", "Tramo %d: decodificar" % i, samples=[str(b + 2), 0], vae=["1", 2])
    return [str(b + 3), 0]


def audio_y_guardar(g, imgs, dur, prefijo):
    T(g, 90, "MMAudioModelLoader", "MMAudio large 44k NSFW", mmaudio_model="mmaudio_large_44k_nsfw_fp16.safetensors",
      base_precision="fp16")
    T(g, 91, "MMAudioFeatureUtilsLoader", "MMAudio utilidades", vae_model="mmaudio_vae_44k_fp16.safetensors",
      synchformer_model="mmaudio_synchformer_fp16.safetensors",
      clip_model="apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors", mode="44k", precision="fp16")
    T(g, 92, "MMAudioSampler", "Audio (prompt del nodo)", mmaudio_model=["90", 0], feature_utils=["91", 0], images=imgs,
      duration=dur, steps=25, cfg=4.5, seed=["20", 0], prompt=["2", 2], negative_prompt=["2", 3],
      mask_away_clip=False, force_offload=True)
    T(g, 93, "CreateVideo", "Vídeo con audio", images=imgs, fps=24.0, audio=["92", 0])
    T(g, 94, "SaveVideo", "Guardar", video=["93", 0], filename_prefix=prefijo, format="mp4", codec="h264")


os.makedirs(a.dest, exist_ok=True)
# 7: un clip
g = {}
base(g, 1)
imgs = tramo(g, 100, 1, ["2", 0], ["10", 0], ["13", 0])
audio_y_guardar(g, imgs, round(a.frames / 24, 3), "video/animar")
p7 = os.path.join(a.dest, "7 Animar con receta (API).json")
json.dump(g, open(p7, "w"), ensure_ascii=False, indent=1)

# 8: video largo
g = {}
base(g, a.tramos)
T(g, 21, "ShowText|pysssss", "Prompts de los tramos", text=["2", 5])
start, total = ["10", 0], None
for i in range(1, a.tramos + 1):
    b = 100 + i * 10
    T(g, b + 9, "RafaElegirTramo", "Tramo %d: su prompt" % i, segmentos=["2", 5], numero=i)
    if a.clip == "ultimo" and i > 1:
        T(g, b + 8, "CLIPVisionEncode", "Tramo %d: CLIP vision del último fotograma" % i, crop="center",
          clip_vision=["7", 0], image=start)
        clip_out = [str(b + 8), 0]
    else:
        clip_out = ["13", 0]
    imgs = tramo(g, b, i, [str(b + 9), 0], start, clip_out)
    T(g, b + 4, "ImageFromBatch", "Tramo %d: último fotograma (arranque del siguiente)" % i, image=imgs,
      batch_index=a.frames - 1, length=1)
    start = [str(b + 4), 0]
    if total is None:
        total = imgs
    else:
        T(g, b + 5, "ImageFromBatch", "Tramo %d: sin su primer fotograma (repite el anterior)" % i, image=imgs,
          batch_index=1, length=a.frames - 1)
        T(g, b + 6, "ImageBatch", "Coser tramo %d" % i, image1=total, image2=[str(b + 5), 0])
        total = [str(b + 6), 0]
dur = round((a.frames + (a.tramos - 1) * (a.frames - 1)) / 24, 3)
audio_y_guardar(g, total, dur, "video/largo")
p8 = os.path.join(a.dest, "8 Video largo (API).json")
json.dump(g, open(p8, "w"), ensure_ascii=False, indent=1)
print("ok", p7, p8, "| clip", a.clip, "| frames", a.frames, "| tramos", a.tramos, "| duracion", dur, "s")
