# -*- coding: utf-8 -*-
"""
rafa_video.py — Cargar imagen con receta (Rafa) + Prompt de video (Rafa)
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes

Para animar una imagen que ya gusta sin escribir el prompt de video a mano:

  Cargar imagen con receta ──IMAGE──────────────► (WanImageToVideo / el WF de video)
           │ receta (JSON)                 ┌────► prompt_video ──► CLIPTextEncode (+)
           └──────────────► Prompt de video┼────► negative_video ► WanVideoNAG / CLIPTextEncode (-)
                 movimiento ─┘   (Claude,  ├────► prompt_audio ──► MMAudioSampler.prompt
                 (Rafa, ES)      con la    └────► negative_audio ► MMAudioSampler.negative_prompt
                                 imagen)

- La receta (rafa_receta.py) da la intencion: la escena que pidio Rafa y el prompt
  con que se hizo la imagen. Claude VE la imagen (la composicion real: quien esta
  donde y que esta haciendo) y escribe un prompt de MOVIMIENTO y CAMARA para I2V,
  que continua la accion que ya muestra la imagen, mas el prompt de audio que la
  acompana (MMAudio) heredando la misma escena.
- Como escribir para cada modelo vive en perfiles .md fuera del repo:
    <RAFA_PERFILES_DIR>/video/<id>.md   (p. ej. wan22_i2v.md)
    <RAFA_PERFILES_DIR>/audio/<id>.md   (p. ej. mmaudio.md)
  Si no existen, se usan las reglas por defecto de este archivo.
- Wan no conoce los triggers de los LoRAs de imagen: el prompt de video nombra a
  la gente por posicion y rasgos visibles, nunca por trigger.
- Negative del video: el negative por defecto de Wan (en chino, del perfil) mas los
  terminos que Claude anada para esta escena. A CFG 1 solo actua con NAG.

Logica en funciones sin ComfyUI (construir_*, postprocesar, ...) para la futura app.
"""

import base64
import hashlib
import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import rafa_prompt_studio as rps
    from . import rafa_receta as rr
except ImportError:
    import rafa_prompt_studio as rps
    import rafa_receta as rr

LOG = "[RafaVideo]"
NINGUNO = rps.NINGUNO
CAMARAS = ["fija", "auto", "push-in lento", "pull-out lento", "paneo lento", "orbita lenta", "mano"]
CAMARA_EN = {
    "fija": "static camera, locked-off tripod shot, no zoom",
    "auto": "",
    "push-in lento": "slow push-in towards the action",
    "pull-out lento": "slow pull-out revealing the scene",
    "paneo lento": "slow pan following the action",
    "orbita lenta": "slow orbit around the subjects",
    "mano": "handheld camera with slight natural shake",
}
NSFW_LEVELS = rps.NSFW_LEVELS
INTENSIDADES = ["suave", "media", "intensa"]

# Mismo bloqueo que Ideas, en ingles y en espanol (Rafa escribe el movimiento en espanol)
_BLOQUEO_ES_RE = re.compile(
    r"\b(j[oó]ven(es)?|chic[oa]s?|chaval(es)?|niñ[oa]s?|adolescentes?|menor(es)? de edad|juvenil(es)?|"
    r"crías?|muchach[oa]s?|imberbes?)\b", re.I)


def terminos_bloqueados(text: str) -> List[str]:
    t = text or ""
    return sorted(set(rps.terminos_bloqueados(t)) | {m.group(0).lower() for m in _BLOQUEO_ES_RE.finditer(t)})


# ============================================================
# Reglas por defecto (si no hay perfil .md)
# ============================================================

# Negative por defecto de Wan 2.1/2.2 (sample_neg_prompt de los configs oficiales)
WAN_NEG_DEFAULT = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，"
                   "低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，"
                   "毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")
WAN_NEG_GRUPO = "背景人很多"  # «mucha gente al fondo»: va contra las escenas de grupo

VIDEO_DEFAULT = """Image-to-video with Wan 2.2 (14B I2V, accelerated 4-step merges such as Rapid AIO / Remix).
- The image already fixes who is there, what they look like, the place and the light. Do NOT re-describe looks, clothes or setting: describe MOTION and CAMERA.
- Structure: the main action continuing what the image shows (who does what to whom, with concrete verbs and rhythm), then secondary motion (bodies reacting, belly and flesh moving, breathing, facial expression), then the camera.
- One main action per clip (about 3-5 seconds). No scene changes, no new people, no cuts.
- Refer to people by position and visible traits ("the bald man on the left", "the heavy hairy man lying on his back"), never by names: the video model does not know them.
- Explicit acts are named plainly when the NSFW level asks for it.
- Accelerated merges slow motion down: say the pace explicitly ("steady fast rhythm", "keeps thrusting hard") when the action needs energy.
- If the camera is fixed, say so: these merges tend to zoom towards whatever the prompt names.
- 40-90 words, one paragraph, present tense, English."""

AUDIO_DEFAULT = """MMAudio (video-to-audio, trained on short clips with sound-event labels and captions).
- Write a short sound description, 6-20 words, comma-separated sound events: what is heard, not what is seen.
- Use non-verbal human sounds (moans, grunts, heavy breathing, gasps); MMAudio cannot produce intelligible speech.
- Add the sounds of the action (skin slapping, wet sounds, bed creaking) and of the place (room tone, shower water, wind).
- Negative: music and speech by default, plus anything that does not fit the scene (for example a female voice).
- English."""

AUDIO_NEG_DEFAULT = "music, singing, speech, talking, female voice"


def _perfil(sub: str, pid: str) -> Tuple[Dict[str, Any], str]:
    raw = rps._read(os.path.join(sub, pid + ".md")) if pid and pid != NINGUNO else None
    if raw is None:
        return {}, ""
    meta, body = rps.parse_md(raw)
    return meta, rps.body_para_claude(body)


def opciones(sub: str, defecto: str) -> List[str]:
    ids = rps._list_ids(sub)
    return ids if ids else [defecto]


# ============================================================
# Peticion a Claude (sin red; testeable)
# ============================================================

SYSTEM_CORE = """You write the prompts that animate a still image into a short video clip, plus the sound for that clip, for Rafa's adult, photorealistic, explicit work between adult men.

ABSOLUTE SAFETY RULE (non-negotiable): NEVER write "young", "younger", "youth", "teen", "boy" or any variant. Every person is an adult man. Use "man", "adult man", "mature man".

Adult content: explicit sex between adults is a normal part of this work; name acts and anatomy directly when the NSFW level asks for it. No euphemisms, no moralising.

You receive: the IMAGE to animate (look at it carefully: who is where, which bodies touch, what act is already happening), the RECIPE of how the image was made (Rafa's original scene request and the image prompt: they tell you the intention of the scene), and Rafa's request for the motion (in Spanish, maybe empty). If Rafa says nothing, continue the action the image already shows, in the way the original scene intended.

Only animate what is in the image. If the image prompt and the image disagree, trust the image.

OUTPUT FORMAT: reply ONLY with valid JSON, no text before or after, no markdown fences:
{
  "accion_vista": "one sentence in Spanish: what is happening in the image",
  "prompt_video": "the video prompt in English",
  "negative_extra": "extra negative terms in English for this scene, comma-separated (can be empty)",
  "prompt_audio": "the sound description in English (empty if no audio is asked)",
  "negative_audio": "sounds to avoid, comma-separated (empty if no audio is asked)",
  "razonamiento": "brief explanation in Spanish of your choices"
}"""


def construir_system(video_meta: Dict[str, Any], video_body: str, audio_body: str, con_audio: bool) -> str:
    parts = [SYSTEM_CORE,
             f"# VIDEO MODEL: {video_meta.get('nombre') or 'Wan 2.2 I2V'}\n\n{video_body or VIDEO_DEFAULT}"]
    if con_audio:
        parts.append(f"# AUDIO MODEL\n\n{audio_body or AUDIO_DEFAULT}")
    return ("\n\n" + "=" * 50 + "\n\n").join(parts)


def construir_peticion(receta: Dict[str, Any], movimiento: str, camara: str, intensidad: str, nsfw: str,
                       duracion_s: float, con_audio: bool, extra: str = "") -> str:
    lines = []
    esc = (receta or {}).get("escena") or ""
    pr = (receta or {}).get("prompt") or ""
    if esc or pr:
        lines.append("RECIPE OF THE IMAGE")
        if esc:
            lines.append(f"Rafa's original scene request: {esc}")
        if pr:
            lines.append(f"Image prompt: {pr}")
    else:
        lines.append("RECIPE OF THE IMAGE: none (work only from the image).")
    lines.append(f"\nRAFA'S MOTION REQUEST: {movimiento.strip() or '(none: continue the action the image shows)'}")
    lines.append(f"NSFW LEVEL: {nsfw}." + (" Explicit sex, named." if nsfw == "explicit" else
                                           " Nudity or tension, no explicit acts." if nsfw == "suggestive"
                                           else " No nudity, no sexual content."))
    lines.append(f"INTENSITY OF THE MOTION: {intensidad} "
                 + {"suave": "(slow, sensual)", "media": "(natural pace)", "intensa": "(fast, vigorous, energetic)"}
                 .get(intensidad, ""))
    cam = CAMARA_EN.get(camara, "")
    lines.append("CAMERA: " + (f"{cam} (write it at the end of the prompt)." if cam
                               else "choose what suits the action; prefer a static camera unless motion helps."))
    lines.append(f"CLIP LENGTH: about {duracion_s:.1f} seconds.")
    if not con_audio:
        lines.append("NO AUDIO: leave prompt_audio and negative_audio empty.")
    if extra.strip():
        lines.append("EXTRA INSTRUCTIONS FROM RAFA (take priority over defaults):\n" + extra.strip())
    return "\n".join(lines)


def triggers_de(receta: Dict[str, Any]) -> List[str]:
    out = []
    for c in (receta or {}).get("personajes") or []:
        try:
            out.append(rps.load_personaje(c)["trigger"])
        except Exception:
            pid = str(c).partition("/")[0]
            if pid:
                out.append(pid)
    return [t for t in out if t]


def montar_negative(base_neg: str, extra: str, grupo: bool) -> str:
    neg = base_neg
    if grupo and WAN_NEG_GRUPO in neg:
        neg = re.sub(r"[，,]?\s*" + WAN_NEG_GRUPO, "", neg).strip("，, ")
    extra = (extra or "").strip().strip(",")
    return f"{neg}, {extra}" if neg and extra else (neg or extra)


def postprocesar(data: Dict[str, Any], receta: Dict[str, Any], camara: str, con_audio: bool,
                 video_meta: Dict[str, Any], audio_meta: Dict[str, Any]) -> Dict[str, Any]:
    avisos: List[str] = []
    pv = str(data.get("prompt_video") or "").strip()
    cam = CAMARA_EN.get(camara, "")
    if cam and camara == "fija" and "static" not in pv.lower() and "fixed camera" not in pv.lower():
        pv = pv.rstrip(". ") + ". " + cam[0].upper() + cam[1:] + "."
        avisos.append("Camara fija anadida por el codigo (Claude no la escribio).")
    for t in triggers_de(receta):
        if re.search(r"\b" + re.escape(t) + r"\b", pv, re.I):
            avisos.append(f"El prompt de video nombra el trigger «{t}»: Wan no lo conoce. Revisalo.")
    n_pers = len((receta or {}).get("personajes") or [])
    grupo = n_pers > 1 or bool(re.search(r"\b(men|group|three|four|five|several|others)\b", pv, re.I))
    neg_base = str(video_meta.get("negative") or WAN_NEG_DEFAULT)
    nv = montar_negative(neg_base, str(data.get("negative_extra") or ""), grupo)
    pa = str(data.get("prompt_audio") or "").strip() if con_audio else ""
    na = ""
    if con_audio:
        na_base = str(audio_meta.get("negative") or AUDIO_NEG_DEFAULT)
        na_extra = str(data.get("negative_audio") or "").strip()
        vistos = {x.strip().lower() for x in na_base.split(",")}
        nuevos = [x.strip() for x in na_extra.split(",") if x.strip() and x.strip().lower() not in vistos]
        na = ", ".join([na_base] + nuevos) if nuevos else na_base
    nw = len(pv.split())
    if nw and (nw < 20 or nw > 140):
        avisos.append(f"Prompt de video de {nw} palabras (lo esperado, 40-90).")
    bloqueados = terminos_bloqueados(" ".join([pv, nv, pa, na]))
    return {"prompt_video": pv, "negative_video": nv, "prompt_audio": pa, "negative_audio": na,
            "accion_vista": str(data.get("accion_vista") or "").strip(),
            "razonamiento": str(data.get("razonamiento") or "").strip(),
            "avisos": avisos, "bloqueados": bloqueados}


def imagen_a_b64(imagen, lado_max: int = 1024) -> Optional[str]:
    """IMAGE de ComfyUI (tensor [B,H,W,C] 0-1) -> PNG base64 del primer fotograma."""
    if imagen is None:
        return None
    import numpy as np
    from PIL import Image
    arr = imagen[0].cpu().numpy() if hasattr(imagen, "cpu") else np.asarray(imagen)[0]
    im = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype("uint8"))
    im.thumbnail((lado_max, lado_max))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def leer_receta_input(receta: Any) -> Dict[str, Any]:
    if isinstance(receta, dict):
        return receta
    if isinstance(receta, str) and receta.strip():
        try:
            r = json.loads(receta)
            return r if isinstance(r, dict) else {}
        except Exception:
            return {"escena": receta.strip(), "origen": "texto"}
    return {}


# ============================================================
# Nodos
# ============================================================

class RafaCargarReceta:
    """Como Load Image, pero ademas lee del PNG la receta (escena, prompt, personajes)."""

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        d = folder_paths.get_input_directory()
        files = [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
        files = folder_paths.filter_files_content_types(files, ["image"])
        return {"required": {"image": (sorted(files), {"image_upload": True})}}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("imagen", "receta", "escena", "prompt_original")
    FUNCTION = "cargar"
    CATEGORY = "rafa/video"

    def cargar(self, image):
        import folder_paths
        import numpy as np
        import torch
        from PIL import Image, ImageOps
        path = folder_paths.get_annotated_filepath(image)
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            t = torch.from_numpy(np.array(im).astype(np.float32) / 255.0)[None, ...]
        rec = rr.receta_de_png(path)
        for a in rec.get("avisos", []):
            print(f"{LOG} {a}")
        print(f"{LOG} receta de {rec.get('archivo')}: origen={rec.get('origen')}")
        return (t, json.dumps(rec, ensure_ascii=False), rec.get("escena") or "", rec.get("prompt") or "")

    @classmethod
    def IS_CHANGED(cls, image):
        import folder_paths
        h = hashlib.sha256()
        with open(folder_paths.get_annotated_filepath(image), "rb") as fh:
            h.update(fh.read())
        reg = rr.registro_path()
        if os.path.isfile(reg):
            h.update(str(os.path.getmtime(reg)).encode())
        return h.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        import folder_paths
        if not folder_paths.exists_annotated_filepath(image):
            return f"No existe la imagen: {image}"
        return True


class RafaPromptVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "movimiento": ("STRING", {"multiline": True, "default": "",
                                          "tooltip": "Que quieres que pase en el clip, en espanol. Vacio = que siga "
                                                     "la accion que ya muestra la imagen."}),
                "perfil_video": (opciones("video", "wan22_i2v"), {}),
                "camara": (CAMARAS, {"default": "fija"}),
                "intensidad": (INTENSIDADES, {"default": "media"}),
                "nsfw": (NSFW_LEVELS, {"default": "explicit"}),
                "duracion_s": ("FLOAT", {"default": 3.4, "min": 1.0, "max": 20.0, "step": 0.1}),
                "con_audio": ("BOOLEAN", {"default": True}),
                "creatividad": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff,
                                 "tooltip": "Fijo = cache (no llama a la API). Cambialo para otra version."}),
            },
            "optional": {
                "imagen": ("IMAGE", {"tooltip": "La imagen a animar: Claude la mira para ver la accion real."}),
                "receta": ("STRING", {"forceInput": True,
                                      "tooltip": "Salida 'receta' de Cargar imagen con receta (o una escena a mano)."}),
                "perfil_audio": (opciones("audio", "mmaudio"), {}),
                "api_key": ("STRING", {"default": "", "tooltip": "Vacio = ANTHROPIC_API_KEY."}),
                "modelo_claude": ("STRING", {"default": "claude-sonnet-4-6"}),
                "extra": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt_video", "negative_video", "prompt_audio", "negative_audio", "razonamiento")
    FUNCTION = "generar"
    CATEGORY = "rafa/video"

    @classmethod
    def IS_CHANGED(cls, perfil_video="", perfil_audio="mmaudio", **kwargs):
        # El resto de inputs ya entra en la cache de ComfyUI; aqui solo el contenido de los perfiles.
        h = hashlib.sha256()
        for rel in (os.path.join("video", f"{perfil_video}.md"), os.path.join("audio", f"{perfil_audio}.md")):
            h.update((rps._read(rel) or "<missing>").encode("utf-8"))
        return h.hexdigest()

    @staticmethod
    def preparar(receta, movimiento, perfil_video, perfil_audio, camara, intensidad, nsfw, duracion_s,
                 con_audio, extra) -> Dict[str, Any]:
        rec = leer_receta_input(receta)
        vmeta, vbody = _perfil("video", perfil_video)
        ameta, abody = _perfil("audio", perfil_audio) if con_audio else ({}, "")
        avisos = []
        if not vbody:
            avisos.append(f"No hay perfil video/{perfil_video}.md: reglas por defecto del codigo.")
        if con_audio and not abody:
            avisos.append(f"No hay perfil audio/{perfil_audio}.md: reglas por defecto del codigo.")
        avisos += [f"Receta: {a}" for a in rec.get("avisos", [])]
        if not rec:
            avisos.append("Sin receta: Claude solo tiene la imagen y tu peticion.")
        return {"receta": rec, "vmeta": vmeta, "ameta": ameta, "avisos": avisos,
                "system": construir_system(vmeta, vbody, abody, bool(con_audio)),
                "peticion": construir_peticion(rec, movimiento, camara, intensidad, nsfw, float(duracion_s),
                                               bool(con_audio), extra or "")}

    def generar(self, movimiento, perfil_video, camara, intensidad, nsfw, duracion_s, con_audio,
                creatividad, seed, imagen=None, receta="", perfil_audio="mmaudio", api_key="",
                modelo_claude="claude-sonnet-4-6", extra=""):
        if rps.anthropic is None:
            raise RuntimeError("Falta el SDK anthropic (requirements.txt del repo)")
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("No hay API key: ANTHROPIC_API_KEY o el input api_key.")
        if terminos_bloqueados(movimiento + " " + (extra or "")):
            raise ValueError("La peticion contiene terminos prohibidos (regla del project). Usa man / adult man.")
        prep = self.preparar(receta, movimiento, perfil_video, perfil_audio, camara, intensidad, nsfw,
                             duracion_s, con_audio, extra)
        content: List[Dict[str, Any]] = []
        b64 = imagen_a_b64(imagen)
        if b64:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
        else:
            prep["avisos"].append("Sin imagen conectada: Claude no ve la composicion.")
        content.append({"type": "text", "text": prep["peticion"]})
        client = rps.anthropic.Anthropic(api_key=key)
        model = (modelo_claude or "").strip() or "claude-sonnet-4-6"
        messages = [{"role": "user", "content": content}]
        res = None
        for intento in (1, 2):
            api_kwargs = dict(model=model, max_tokens=2048,
                              temperature=max(0.0, min(1.0, float(creatividad))),
                              system=[{"type": "text", "text": prep["system"],
                                       "cache_control": {"type": "ephemeral"}}],
                              messages=messages)
            try:
                msg = rps.create_with_fallback(client, api_kwargs)
            except Exception as e:
                raise RuntimeError(f"Error de la API: {e}")
            raw = rps.extract_text(msg)
            u = getattr(msg, "usage", None)
            if u is not None:
                print(f"{LOG} seed={seed} intento={intento} in:{u.input_tokens} out:{u.output_tokens}")
            try:
                data = rps.parse_json(raw)
            except Exception as e:
                if intento == 1:
                    messages = messages + [{"role": "assistant", "content": raw},
                                           {"role": "user", "content": "Reply again with ONLY the JSON object."}]
                    continue
                raise RuntimeError(f"La respuesta no es JSON valido ({e}): {raw[:300]}")
            res = postprocesar(data, prep["receta"], camara, bool(con_audio), prep["vmeta"], prep["ameta"])
            if not res["bloqueados"]:
                break
            if intento == 1:
                messages = messages + [{"role": "assistant", "content": raw},
                                       {"role": "user", "content": "Rewrite the JSON: it contains forbidden terms: "
                                        + ", ".join(res["bloqueados"]) + ". Every person is an adult man."}]
        if res is None:
            raise RuntimeError("Sin respuesta valida de la API.")
        if res["bloqueados"]:
            raise RuntimeError("Prompt bloqueado (regla del project): contiene "
                               + ", ".join(res["bloqueados"]) + ". No se emite.")
        avisos = prep["avisos"] + res["avisos"]
        partes = []
        if avisos:
            partes.append("AVISOS:\n" + "\n".join("- " + a for a in avisos))
        if res["accion_vista"]:
            partes.append("Lo que ve en la imagen: " + res["accion_vista"])
        if res["razonamiento"]:
            partes.append(res["razonamiento"])
        partes.append("Receta: origen " + str(prep["receta"].get("origen", "ninguna")))
        for a in avisos:
            print(f"{LOG} AVISO: {a}")
        return (res["prompt_video"], res["negative_video"], res["prompt_audio"], res["negative_audio"],
                "\n\n----\n\n".join(partes))


NODE_CLASS_MAPPINGS = {"RafaCargarReceta": RafaCargarReceta, "RafaPromptVideo": RafaPromptVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"RafaCargarReceta": "Cargar imagen con receta (Rafa)",
                              "RafaPromptVideo": "Prompt de vídeo (Rafa)"}
