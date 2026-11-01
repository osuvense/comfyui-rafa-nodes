# -*- coding: utf-8 -*-
"""
rafa_prompt_studio.py — Prompt Studio (nodo de prompts v2)
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes

Diseno: [REF]-nodo-prompt-generator.md § 8 (knowledge del project, no en el repo).

Lo que cambia con el tiempo vive en archivos .md FUERA del repo (perfiles):
  <RAFA_PERFILES_DIR>/                      (por defecto /workspace/perfiles_prompt)
    modelos/<id>.md      base de inferencia: como escribir, negative, resoluciones
    lexicos/<id>.md      vocabulario de un finetune/merge (p. ej. SNOFS)
    personajes/<id>.md   trigger, class, frases reservadas, LoRAs por base, acabado
    estetica.md          estetica por defecto (taste profile)
Cada .md lleva cabecera YAML entre '---' y cuerpo markdown. Los archivos que
empiezan por '_' se ignoran. Las secciones '## Historial' y '## Fuentes' del
cuerpo no se envian a Claude (no aportan y cuestan tokens).

Montaje determinista: Claude escribe la escena con marcadores [P1]-[P3]. El codigo
sustituye la PRIMERA aparicion de cada marcador por la apertura del personaje
("Alfa, a heavyset older man") y las siguientes por su trigger. Despues valida
el texto: 'young' y variantes = bloqueo duro; marcadores que faltan, class
reservada usada para otro y acabados que evitar = avisos (salida 'razonamiento').

Variantes de personaje (un personaje con dos versiones, A y B): en la cabecera YAML,
    variantes:
      A: {trigger: ..., class: ..., ...}   # claves que sobreescriben las de arriba
Aparecen en el desplegable como '<id>/A'.

Coincidencia LoRA-base: un entrenamiento cuenta para la base elegida si su 'base'
es el id del perfil de modelo o su campo 'familia_lora' (p. ej. zimage_turbo y
zimage_base comparten familia_lora: zimage).

Lo aprendido del nodo viejo que se conserva: cache por hash de inputs (incluye el
contenido de los perfiles usados), prompt caching de Anthropic con los perfiles en
el bloque estable, compat de 'temperature' con el SDK (>=1.0 via extra_body) y
NADA de widgets dinamicos de display (incidente de coste del 10/06/2026).
El nodo no carga LoRAs: eso sigue en la cadena de loaders.
"""

import os
import re
import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple

try:
    import anthropic
except Exception:  # los tests y el listado de perfiles no necesitan el SDK
    anthropic = None

try:
    import yaml
except Exception:
    yaml = None


LOG = "[RafaPromptStudio]"
NINGUNO = "ninguno"
SIN_PERFILES = "(sin perfiles)"
DEFAULT_DIRS = ("/workspace/perfiles_prompt",)
MAX_PERSONAJES = 3

NSFW_LEVELS = ["explicit", "suggestive", "sfw"]
FRAMINGS = ["auto", "close-up", "portrait", "upper body", "full body", "genital close-up"]
ESTILOS = ["caption", "compacto"]


# ============================================================
# Perfiles
# ============================================================

def perfiles_dir() -> Optional[str]:
    env = os.getenv("RAFA_PERFILES_DIR", "").strip()
    cands = ([env] if env else []) + list(DEFAULT_DIRS) + [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "perfiles_prompt"),
    ]
    for d in cands:
        if d and os.path.isdir(d):
            return d
    return None


_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


def parse_md(text: str) -> Tuple[Dict[str, Any], str]:
    """Cabecera YAML + cuerpo. Sin cabecera -> ({}, texto)."""
    m = _FM_RE.match(text.lstrip("﻿"))
    if not m:
        return {}, text
    if yaml is None:
        raise RuntimeError("Falta PyYAML (pip install pyyaml) para leer los perfiles")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, m.group(2)


_SECCIONES_FUERA = ("historial", "fuentes", "fuente")


def body_para_claude(body: str) -> str:
    """Quita las secciones '## Historial' / '## Fuentes' del cuerpo."""
    out, skip = [], False
    for line in body.splitlines():
        if line.startswith("## "):
            skip = line[3:].strip().lower().startswith(_SECCIONES_FUERA)
        if not skip:
            out.append(line)
    return "\n".join(out).strip()


def _list_ids(sub: str) -> List[str]:
    d = perfiles_dir()
    if not d:
        return []
    p = os.path.join(d, sub)
    if not os.path.isdir(p):
        return []
    return sorted(f[:-3] for f in os.listdir(p)
                  if f.endswith(".md") and not f.startswith(("_", ".")))


def _read(rel: str) -> Optional[str]:
    d = perfiles_dir()
    if not d:
        return None
    p = os.path.join(d, rel)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as fh:
        return fh.read()


def load_profile(sub: str, pid: str) -> Tuple[Dict[str, Any], str, str]:
    """(meta, cuerpo, texto crudo). Lanza ValueError si no existe."""
    raw = _read(os.path.join(sub, pid + ".md"))
    if raw is None:
        raise ValueError(f"No existe el perfil {sub}/{pid}.md en {perfiles_dir()}")
    meta, body = parse_md(raw)
    return meta, body, raw


def personaje_options() -> List[str]:
    opts = [NINGUNO]
    for pid in _list_ids("personajes"):
        opts.append(pid)
        try:
            meta, _, _ = load_profile("personajes", pid)
            for var in (meta.get("variantes") or {}):
                opts.append(f"{pid}/{var}")
        except Exception as e:
            print(f"{LOG} perfil personajes/{pid}.md ilegible: {e}")
    return opts


def load_personaje(choice: str) -> Dict[str, Any]:
    pid, _, var = choice.partition("/")
    meta, body, raw = load_profile("personajes", pid)
    meta = dict(meta)
    if var:
        vmap = meta.get("variantes") or {}
        if var not in vmap:
            raise ValueError(f"El personaje {pid} no tiene la variante {var}")
        meta.update(vmap[var] or {})
    meta.pop("variantes", None)
    trigger = str(meta.get("trigger") or "").strip()
    cls = str(meta.get("class") or "").strip()
    if not trigger:
        raise ValueError(f"personajes/{pid}.md: falta 'trigger'")
    reservado = [str(r).strip() for r in (meta.get("reservado") or []) if str(r).strip()]
    if cls and cls not in reservado:
        reservado.append(cls)
    # En los ejemplos del perfil la class va como <CLASS>
    body_c = body_para_claude(body).replace("<CLASS>", cls or trigger)
    return {
        "choice": choice, "id": pid, "variante": var, "meta": meta,
        "trigger": trigger, "class": cls, "reservado": reservado,
        "loras": meta.get("loras") or [], "body": body_c, "raw": raw,
        "acabado_pedir": str(meta.get("acabado_pedir") or "").strip(),
        "acabado_evitar": [str(x) for x in (meta.get("acabado_evitar") or [])],
        "fijos": _lista_dicts(meta.get("rasgos_fijos"), ("grupo", "frase")),
        "class_prefijo": str(meta.get("class_prefijo") or "").strip(),
        "estados": _lista_dicts(meta.get("estados"), ("id", "grupo", "frase", "si_no_se_pide")),
        "nombrar_fijos": True, "pedidos": [],
    }


def _lista_dicts(v: Any, claves: Tuple[str, ...]) -> List[Dict[str, str]]:
    out = []
    for d in v or []:
        if isinstance(d, dict) and str(d.get("frase") or "").strip():
            out.append({k: str(d.get(k) or "").strip() for k in claves})
    return out


def _article(phrase: str) -> str:
    return "an" if phrase[:1].lower() in "aeiou" else "a"


def _y(frases: List[str]) -> str:
    return frases[0] if len(frases) == 1 else ", ".join(frases[:-1]) + " and " + frases[-1]


def rasgos_apertura(p: Dict[str, Any]) -> List[str]:
    """Frases que siguen a la class: estados pedidos, rasgos fijos que no pisa ningun
    estado pedido (si nombrar_fijos) y el 'si_no_se_pide' de los estados no pedidos."""
    pedidos = [e for e in p.get("estados", []) if e["id"] in p.get("pedidos", [])]
    grupos_pedidos = {e["grupo"] for e in pedidos if e["grupo"]}
    frases = [e["frase"] for e in pedidos]
    if p.get("nombrar_fijos", True):
        frases += [f["frase"] for f in p.get("fijos", []) if f["grupo"] not in grupos_pedidos]
    con = ", with " + _y(frases) if frases else ""
    sin = [e["si_no_se_pide"] for e in p.get("estados", [])
           if e["id"] not in p.get("pedidos", []) and e["si_no_se_pide"]
           and e["grupo"] not in grupos_pedidos]
    return [con] + ([", " + _y(sin)] if sin else [])


def apertura(p: Dict[str, Any]) -> str:
    """'Alfa, a heavyset older man[, with ...]' (como abren sus captions)."""
    if not p["class"]:
        base = p["trigger"]
    else:
        # class_prefijo (p. ej. "morbidly obese") refuerza la class; va con los rasgos fijos
        pre = p.get("class_prefijo", "") if p.get("nombrar_fijos", True) else ""
        frase = f"{pre} {p['class']}".strip()
        base = f'{p["trigger"]}, {_article(frase)} {frase}'
    return base + "".join(rasgos_apertura(p))


# ============================================================
# Montaje y validacion
# ============================================================

# Regla del project: prohibido young/younger/young man y variantes. Se amplia a
# terminos que tambien sugieren menores. Bloqueo duro.
_BLOQUEO_RE = re.compile(
    r"\b(young\w*|youth\w*|teen\w*|boys?|boyish|child\w*|kids?|minors?|underage\w*|juvenile\w*)\b",
    re.I)
_MARKER_RE = re.compile(r"\[P(\d+)\]")


def terminos_bloqueados(text: str) -> List[str]:
    return sorted({m.group(0).lower() for m in _BLOQUEO_RE.finditer(text or "")})


def montar(text: str, personajes: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """Sustituye [Pn]. Devuelve (texto, avisos)."""
    avisos: List[str] = []
    vistos = set()

    def repl(m):
        n = int(m.group(1))
        if n < 1 or n > len(personajes):
            avisos.append(f"Marcador [P{n}] sin personaje: eliminado.")
            return ""
        p = personajes[n - 1]
        if n not in vistos:
            vistos.add(n)
            return apertura(p)
        return p["trigger"]

    out = _MARKER_RE.sub(repl, text or "")
    # Posesivo en la primera mencion ("Alfa, a heavyset older man's") rompe la apertura
    for p in personajes:
        if p["class"] and re.search(re.escape(apertura(p)) + r"'s\b", out):
            avisos.append(f"{p['trigger']}: la primera mencion va en posesivo; revisa la apertura.")
    for i, p in enumerate(personajes, 1):
        if i not in vistos:
            avisos.append(f"Falta el marcador [P{i}] ({p['trigger']}): el trigger no esta en el prompt.")
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out).strip()
    return out, avisos


def validar(text: str, personajes: List[Dict[str, Any]]) -> List[str]:
    """Avisos sobre el texto ya montado (sin el bloqueo duro, que va aparte)."""
    avisos = []
    low = text.lower()
    for p in personajes:
        if not re.search(r"\b" + re.escape(p["trigger"]) + r"\b", text):
            avisos.append(f"El trigger {p['trigger']} no aparece en el prompt.")
    # class reservada: cada personaje que la tiene la usa una vez (su apertura)
    frases = {}
    for p in personajes:
        for r in p["reservado"]:
            frases.setdefault(r.lower(), 0)
            if p["class"].lower() == r.lower():
                frases[r.lower()] += 1
    for frase, esperado in frases.items():
        n = len(re.findall(r"\b" + re.escape(frase) + r"\b", low))
        if n > esperado:
            avisos.append(f"La frase reservada «{frase}» aparece {n} veces (esperado {esperado}): "
                          f"puede estar describiendo a otra persona.")
    for p in personajes:
        for ev in p["acabado_evitar"]:
            if ev and ev.lower() in low:
                avisos.append(f"Aparece «{ev}», que el perfil de {p['trigger']} pide evitar.")
    return avisos


def avisos_previos(personajes: List[Dict[str, Any]], base_meta: Dict[str, Any]) -> List[str]:
    avisos = []
    base_ids = {str(base_meta.get("id") or ""), str(base_meta.get("familia_lora") or "")} - {""}
    for p in personajes:
        if not any(str(l.get("base", "")) in base_ids for l in p["loras"] if isinstance(l, dict)):
            avisos.append(f"{p['trigger']} no tiene LoRA para la base {base_meta.get('nombre') or base_meta.get('id')}: "
                          f"el trigger no hara nada sin LoRA.")
    clases: Dict[str, List[str]] = {}
    for p in personajes:
        if p["class"]:
            clases.setdefault(p["class"].lower(), []).append(p["trigger"])
    for cls, trig in clases.items():
        if len(trig) > 1:
            avisos.append(f"{' y '.join(trig)} comparten class «{cls}»: riesgo de mezcla de identidades.")
    return avisos


def cerrar_acabado(text: str, personajes: List[Dict[str, Any]], estilo: str) -> str:
    """En estilo caption, el prompt cierra con el acabado del primer personaje."""
    if estilo != "caption" or not personajes:
        return text
    fin = personajes[0]["acabado_pedir"]
    if not fin or fin.lower().rstrip(".") in text.lower():
        return text
    t = text.rstrip()
    if t and t[-1] not in ".!?":
        t += "."
    return (t + " " + fin).strip()


# ============================================================
# System prompt
# ============================================================

SYSTEM_CORE = """You write image-generation prompts for Rafa's diffusion models (adult, photorealistic, explicit work between adult men). Turn the user's scene idea - sometimes vague, sometimes just a few words, often in Spanish - into the best prompt for the TARGET MODEL described below, filling in what the user leaves open.

ABSOLUTE SAFETY RULE (non-negotiable): NEVER write "young", "younger", "youth", "teen", "boy" or any variant. Every person is an adult man. Use "man", "adult man", "mature man". For a contrast in age or body use "slim adult man".

Adult content: explicit sex between adults is a normal part of this work; describe anatomy directly when the scene asks for it. No euphemisms, no moralising.

CHARACTERS WITH A LoRA: write each one as a marker [P1], [P2], [P3], never by name. The code replaces the FIRST appearance of each marker with the character's trigger and class word (for example "Alfa, a heavyset older man"), so the first mention must work as the start of an appositive: "[P1], lying on his back on a bed, ...". Do not put the first mention in the possessive ("[P1]'s ..."). Later mentions of the same marker become the trigger alone and may be possessive ("[P1]'s left hand"). Never write a character's trigger, class word or reserved phrases yourself. Do NOT describe a character's invariant traits (age, build, baldness, mustache, body hair, face, skin, eyes, feet): the LoRA supplies them, and the code adds the short fixed-trait phrase of the profile. Hair and beard states are chosen through "states" (see each character), never written by you. Describe only what varies: pose and limbs, position in the frame, clothing, props, the act, setting, light and the photographic finish, following each character's caption format.

PEOPLE WITHOUT A LoRA: describe them fully and plainly ("another man", "the other man") without ever using any character's reserved phrases.

SEVERAL CHARACTERS: group each one with his own attributes and actions and place him in his own zone of the frame ("at the left of the frame", "in the foreground") so the model does not blend them.

OUTPUT FORMAT: reply ONLY with valid JSON, no text before or after, no markdown fences."""


def output_format(variants: int, negative: bool, con_estados: bool = False) -> str:
    estados = ('\n  "states": {"P1": []},  (optional state ids per marker; empty unless the user asks for them)'
               if con_estados else "")
    neg = ('"negative": "negative prompt in English (the target model uses one)"'
           if negative else '"negative": ""  (this model does not use a negative prompt: leave it empty)')
    s = f"""JSON keys, exactly:
{{
  "prompt": "the positive prompt in English, with [P1]-[P3] markers",
  {neg},
  "variants": [],{estados}
  "razonamiento": "brief explanation in Spanish of your choices"
}}"""
    if variants > 1:
        s += (f'\n\nWrite {variants} DIFFERENT versions in "variants" (the first one equal to "prompt"), '
              "varying composition, pose, framing, setting and detail while keeping the scene the user asked for. "
              "Every version uses the markers.")
    return s


def build_system(base: Tuple[Dict, str], lexico: Optional[Tuple[Dict, str]],
                 personajes: List[Dict[str, Any]], estetica: Optional[str]) -> str:
    """Bloque ESTABLE (cacheado): core + perfiles."""
    bmeta, bbody = base
    parts = [SYSTEM_CORE,
             f"# TARGET MODEL: {bmeta.get('nombre') or bmeta.get('id')}\n\n{body_para_claude(bbody)}"]
    if lexico:
        lmeta, lbody = lexico
        parts.append(f"# LEXICON: {lmeta.get('nombre') or lmeta.get('id')}\n"
                     f"Use these terms for the acts they name, then describe the position in full sentences.\n\n"
                     f"{body_para_claude(lbody)}")
    for i, p in enumerate(personajes, 1):
        var_txt = (f"; ACTIVE VARIANT: {p['variante']} (use only the sections for this variant)"
                   if p.get("variante") else "")
        est_txt = ""
        if p.get("estados"):
            est_txt = ("OPTIONAL STATES of this character (hair, beard...). The code writes them; you never "
                       "describe them. List an id in \"states\" for this marker ONLY if the user explicitly asks "
                       "for that state: " + "; ".join(f'{e["id"]} = "{e["frase"]}"' for e in p["estados"]) + "\n")
        parts.append(f"# CHARACTER [P{i}] (profile; the code writes \"{apertura(p)}\" for you{var_txt})\n"
                     + est_txt +
                     f"Reserved phrases (never use them for anyone else): "
                     f"{', '.join(repr(r) for r in p['reservado']) or '-'}\n"
                     f"Finish to ask for: {p['acabado_pedir'] or '-'}; avoid: "
                     f"{'; '.join(p['acabado_evitar']) or '-'}\n\n{p['body']}")
    if estetica:
        parts.append("# DEFAULT AESTHETIC (for people without a LoRA and for whatever the user leaves open; "
                     "NEVER to describe a character with a LoRA)\n\n" + estetica)
    return ("\n\n" + "=" * 50 + "\n\n").join(parts)


def build_variable(nsfw: str, encuadre: str, estilo: str, variants: int,
                   negative: bool, n_pers: int, extra: str, con_estados: bool = False) -> str:
    estilo_txt = {
        "caption": ("STYLE: caption. Write it like the characters' training captions (long, detailed prose, "
                    "one paragraph, ending with the photographic finish). With no character, follow the target "
                    "model's length rules."),
        "compacto": ("STYLE: compact. One short paragraph (about 40-80 words): subject, pose, act, setting, light, "
                     "finish. No secondary detail."),
    }[estilo]
    lines = [
        f"NSFW LEVEL: {nsfw}." + (" Sexual content explicit and named." if nsfw == "explicit" else
                                  " Nudity or tension without explicit sex acts." if nsfw == "suggestive" else
                                  " No nudity, no sexual content."),
        f"FRAMING: {encuadre}." + (" Choose what suits the scene." if encuadre == "auto" else ""),
        estilo_txt,
        (f"CHARACTERS IN THIS IMAGE: {n_pers} (markers [P1]..[P{n_pers}], each used at least once)."
         if n_pers else "NO CHARACTERS WITH A LoRA: do not use markers; describe every person fully."),
    ]
    if extra.strip():
        lines.append("EXTRA INSTRUCTIONS FROM RAFA (take priority over defaults):\n" + extra.strip())
    lines.append(output_format(variants, negative, con_estados))
    return "\n\n".join(lines)


# ============================================================
# Compat 'temperature' (copiado del nodo viejo, § 5.10)
# ============================================================

_TEMP_DEPRECATED_PREFIXES = ("claude-sonnet-5", "claude-opus-4-8", "claude-opus-4-7")
_TEMP_UNSUPPORTED_MODELS: set = set()
_SDK_HAS_TEMPERATURE = None


def _sdk_accepts_temperature() -> bool:
    global _SDK_HAS_TEMPERATURE
    if _SDK_HAS_TEMPERATURE is None:
        try:
            import inspect
            from anthropic.resources.messages import Messages
            _SDK_HAS_TEMPERATURE = "temperature" in inspect.signature(Messages.create).parameters
        except Exception:
            _SDK_HAS_TEMPERATURE = True
    return bool(_SDK_HAS_TEMPERATURE)


def _temp_via_extra_body(kw: dict) -> dict:
    t = kw.pop("temperature", None)
    if t is None:
        return kw
    eb = dict(kw.get("extra_body") or {})
    eb.setdefault("temperature", t)
    kw["extra_body"] = eb
    return kw


def _strip_temp(kwargs: dict) -> dict:
    kwargs = dict(kwargs)
    kwargs.pop("temperature", None)
    eb = kwargs.get("extra_body")
    if isinstance(eb, dict) and "temperature" in eb:
        eb = {k: v for k, v in eb.items() if k != "temperature"}
        if eb:
            kwargs["extra_body"] = eb
        else:
            kwargs.pop("extra_body", None)
    return kwargs


def _temp_rejected(model: str) -> bool:
    m = str(model or "")
    return m.startswith(_TEMP_DEPRECATED_PREFIXES) or m in _TEMP_UNSUPPORTED_MODELS


def create_with_fallback(client, api_kwargs: dict):
    global _SDK_HAS_TEMPERATURE
    api_kwargs = dict(api_kwargs)
    if _temp_rejected(api_kwargs.get("model")):
        api_kwargs.pop("temperature", None)
    elif not _sdk_accepts_temperature():
        api_kwargs = _temp_via_extra_body(api_kwargs)
    had_temp = "temperature" in api_kwargs or "temperature" in (api_kwargs.get("extra_body") or {})
    try:
        return client.messages.create(**api_kwargs)
    except Exception as e:
        msg = str(e).lower()
        sdk_sig = isinstance(e, TypeError) and "unexpected keyword argument" in msg
        if had_temp and "temperature" in msg and (sdk_sig or "deprecat" in msg
                                                  or "not supported" in msg or "unsupported" in msg):
            if sdk_sig:
                _SDK_HAS_TEMPERATURE = False
            else:
                _TEMP_UNSUPPORTED_MODELS.add(str(api_kwargs.get("model", "")))
            print(f"{LOG} 'temperature' no admitida; se reintenta sin ella.")
            return client.messages.create(**_strip_temp(api_kwargs))
        raise


def extract_text(response) -> str:
    parts = []
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "\n".join(parts).strip()


def parse_json(raw: str) -> Dict[str, Any]:
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`\n ")
        if s.startswith("json"):
            s = s[4:].strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            return json.loads(s[i:j + 1])
        raise


# ============================================================
# Nodo
# ============================================================

class RafaPromptStudio:
    """Prompt Studio: perfiles .md + montaje determinista. Ver docstring del modulo."""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        # ComfyUI vuelve a llamar a INPUT_TYPES en cada /object_info: un perfil
        # nuevo aparece al refrescar las definiciones de nodos.
        bases = _list_ids("modelos") or [SIN_PERFILES]
        lexicos = [NINGUNO] + _list_ids("lexicos")
        pers = personaje_options()
        return {
            "required": {
                "escena": ("STRING", {"multiline": True, "default": "",
                                      "tooltip": "La escena, en espanol o ingles. Los personajes elegidos abajo son P1-P3."}),
                "base": (bases, {"tooltip": "Perfil de modelos/: como escribir para esa base."}),
                "lexico": (lexicos, {"default": NINGUNO}),
                "personaje_1": (pers, {"default": NINGUNO}),
                "personaje_2": (pers, {"default": NINGUNO}),
                "personaje_3": (pers, {"default": NINGUNO}),
                "usar_estetica": ("BOOLEAN", {"default": True,
                                              "tooltip": "estetica.md para personas sin LoRA y lo que no especifiques."}),
                "nsfw": (NSFW_LEVELS, {"default": "explicit"}),
                "encuadre": (FRAMINGS, {"default": "auto"}),
                "estilo": (ESTILOS, {"default": "caption"}),
                "variantes": ("INT", {"default": 1, "min": 1, "max": 6}),
                "creatividad": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff,
                                 "tooltip": "Fijo = cache (no llama a la API). Cambialo para otra version."}),
            },
            "optional": {
                "api_key": ("STRING", {"default": "", "tooltip": "Vacio = ANTHROPIC_API_KEY."}),
                "modelo_claude": ("STRING", {"default": "claude-sonnet-4-6"}),
                "extra": ("STRING", {"multiline": True, "default": ""}),
                "nombrar_rasgos_fijos": ("BOOLEAN", {"default": True,
                                                     "tooltip": "Añade a la apertura del personaje sus rasgos fijos "
                                                                "(rasgos_fijos del perfil). Apagado: solo trigger y class."}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative", "razonamiento")
    FUNCTION = "generar"
    CATEGORY = "rafa"

    # ---------- cache ----------

    @staticmethod
    def _profiles_fingerprint(base, lexico, pers_choices, usar_estetica) -> str:
        h = hashlib.sha256()
        rels = [os.path.join("modelos", f"{base}.md")]
        if lexico and lexico != NINGUNO:
            rels.append(os.path.join("lexicos", f"{lexico}.md"))
        for c in pers_choices:
            if c and c != NINGUNO:
                rels.append(os.path.join("personajes", c.partition("/")[0] + ".md"))
        if usar_estetica:
            rels.append("estetica.md")
        for r in rels:
            h.update(r.encode())
            h.update((_read(r) or "<missing>").encode("utf-8"))
        return h.hexdigest()

    @classmethod
    def IS_CHANGED(cls, escena="", base="", lexico=NINGUNO, personaje_1=NINGUNO,
                   personaje_2=NINGUNO, personaje_3=NINGUNO, usar_estetica=True,
                   nsfw="", encuadre="", estilo="", variantes=1, creatividad=0.8,
                   seed=0, modelo_claude="", extra="", **kwargs):
        # api_key se excluye a proposito. El contenido de los perfiles entra en la clave.
        key = repr((escena, base, lexico, personaje_1, personaje_2, personaje_3,
                    bool(usar_estetica), nsfw, encuadre, estilo, int(variantes),
                    round(float(creatividad), 4), int(seed), modelo_claude, extra,
                    cls._profiles_fingerprint(base, lexico, (personaje_1, personaje_2, personaje_3),
                                              bool(usar_estetica)))
                   + (("sin_rasgos_fijos",) if not kwargs.get("nombrar_rasgos_fijos", True) else ()))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    # ---------- preparacion (sin red; testeable) ----------

    @staticmethod
    def preparar(base, lexico, personajes_sel, usar_estetica, nsfw, encuadre, estilo,
                 variantes, extra, nombrar_fijos=True) -> Dict[str, Any]:
        if base == SIN_PERFILES:
            raise ValueError("No hay perfiles: define RAFA_PERFILES_DIR o sube perfiles_prompt/ al volumen.")
        bmeta, bbody, _ = load_profile("modelos", base)
        bmeta.setdefault("id", base)
        lex = None
        bases_lex: List[str] = []
        if lexico and lexico != NINGUNO:
            lmeta, lbody, _ = load_profile("lexicos", lexico)
            lmeta.setdefault("id", lexico)
            bases_lex = [str(b) for b in (lmeta.get("bases") or [])]
            lex = (lmeta, lbody)
        # Huecos vacios se compactan: P1..Pn son los elegidos, en orden
        personajes = [load_personaje(c) for c in personajes_sel if c and c != NINGUNO]
        for p in personajes:
            p["nombrar_fijos"] = bool(nombrar_fijos)
        avisos = avisos_previos(personajes, bmeta)
        if lex and bases_lex and str(bmeta.get("id")) not in bases_lex \
                and str(bmeta.get("familia_lora") or "") not in bases_lex:
            avisos.append(f"El lexico {lexico} no esta declarado para la base {base}.")
        estetica = None
        if usar_estetica:
            raw = _read("estetica.md")
            if raw is None:
                avisos.append("usar_estetica activo pero no existe estetica.md.")
            else:
                estetica = body_para_claude(parse_md(raw)[1])
        negative = bool(bmeta.get("negative", False))
        stable = build_system((bmeta, bbody), lex, personajes, estetica)
        variable = build_variable(nsfw, encuadre, estilo, max(1, int(variantes)),
                                  negative, len(personajes), extra or "",
                                  any(p["estados"] for p in personajes))
        return {"stable": stable, "variable": variable, "personajes": personajes,
                "avisos": avisos, "negative_ok": negative}

    @staticmethod
    def postprocesar(data: Dict[str, Any], prep: Dict[str, Any], estilo: str) -> Dict[str, Any]:
        pers = [dict(p) for p in prep["personajes"]]
        avisos_est = []
        est = data.get("states") if isinstance(data.get("states"), dict) else {}
        for i, p in enumerate(pers, 1):
            ids = est.get(f"P{i}") or []
            ids = [str(x) for x in ids] if isinstance(ids, list) else []
            validos = {e["id"] for e in p["estados"]}
            for x in ids:
                if x not in validos:
                    avisos_est.append(f"{p['trigger']}: estado «{x}» no existe en su perfil; se ignora.")
            p["pedidos"] = [x for x in ids if x in validos]
            if p["pedidos"]:
                avisos_est.append(f"{p['trigger']}: estados pedidos: {', '.join(p['pedidos'])}.")
        textos = [str(data.get("prompt") or "").strip()]
        var = data.get("variants") or []
        if isinstance(var, list):
            textos += [str(v).strip() for v in var[1:] if str(v).strip()]
        montados, avisos = [], list(avisos_est)
        for i, t in enumerate(textos):
            m, av = montar(t, pers)
            m = cerrar_acabado(m, pers, estilo)
            av += validar(m, pers)
            tag = "" if i == 0 else f"[variante {i + 1}] "
            avisos += [tag + a for a in av]
            montados.append(m)
        negative = str(data.get("negative") or "").strip() if prep["negative_ok"] else ""
        # La regla vale para cualquier prompt, negative incluido
        bloqueados = terminos_bloqueados(" ".join(montados + [negative]))
        return {"prompts": montados, "negative": negative, "avisos": avisos,
                "bloqueados": bloqueados, "razonamiento": str(data.get("razonamiento") or "").strip()}

    # ---------- ejecucion ----------

    def generar(self, escena, base, lexico, personaje_1, personaje_2, personaje_3,
                usar_estetica, nsfw, encuadre, estilo, variantes, creatividad, seed,
                api_key="", modelo_claude="claude-sonnet-4-6", extra="", nombrar_rasgos_fijos=True):
        if not str(escena).strip():
            raise ValueError("La escena no puede estar vacia")
        if anthropic is None:
            raise RuntimeError("Falta el SDK anthropic (requirements.txt del repo)")
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("No hay API key: ANTHROPIC_API_KEY o el input api_key.")

        prep = self.preparar(base, lexico, (personaje_1, personaje_2, personaje_3), bool(usar_estetica),
                             nsfw, encuadre, estilo, variantes, extra, bool(nombrar_rasgos_fijos))
        client = anthropic.Anthropic(api_key=key)
        model = (modelo_claude or "").strip() or "claude-sonnet-4-6"
        messages = [{"role": "user", "content": str(escena)}]

        res = None
        for intento in (1, 2):
            api_kwargs = dict(
                model=model,
                max_tokens=8192 if int(variantes) >= 3 else 4096,
                temperature=max(0.0, min(1.0, float(creatividad))),
                system=[{"type": "text", "text": prep["stable"], "cache_control": {"type": "ephemeral"}},
                        {"type": "text", "text": prep["variable"]}],
                messages=messages,
            )
            try:
                msg = create_with_fallback(client, api_kwargs)
            except Exception as e:
                raise RuntimeError(f"Error de la API: {e}")
            raw = extract_text(msg)
            u = getattr(msg, "usage", None)
            if u is not None:
                print(f"{LOG} base={base} seed={seed} intento={intento} in:{u.input_tokens} "
                      f"out:{u.output_tokens} cache_w:{getattr(u, 'cache_creation_input_tokens', 0) or 0} "
                      f"cache_r:{getattr(u, 'cache_read_input_tokens', 0) or 0}")
            try:
                data = parse_json(raw)
            except Exception as e:
                raise RuntimeError(f"La respuesta no es JSON valido ({e}): {raw[:300]}")
            res = self.postprocesar(data, prep, estilo)
            faltan = [a for a in res["avisos"] if a.startswith("Falta el marcador")]
            if not res["bloqueados"] and not faltan:
                break
            if intento == 1:
                problemas = []
                if res["bloqueados"]:
                    problemas.append("it contains forbidden terms: " + ", ".join(res["bloqueados"]))
                if faltan:
                    problemas.append("some character markers are missing: " + " ".join(faltan))
                print(f"{LOG} reintento: {'; '.join(problemas)}")
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Rewrite the JSON: " + "; ".join(problemas)
                     + ". Every person is an adult man. Keep everything else."},
                ]
        if res["bloqueados"]:
            raise RuntimeError("Prompt bloqueado (regla del project): contiene "
                               + ", ".join(res["bloqueados"]) + ". No se emite.")

        avisos = prep["avisos"] + res["avisos"]
        partes = []
        if avisos:
            partes.append("AVISOS:\n" + "\n".join("- " + a for a in avisos))
        if res["razonamiento"]:
            partes.append(res["razonamiento"])
        if len(res["prompts"]) > 1:
            partes.append("VARIANTES:\n\n" + "\n\n".join(f"[{i + 1}] {p}" for i, p in enumerate(res["prompts"])))
        razonamiento = "\n\n----\n\n".join(partes)
        for a in avisos:
            print(f"{LOG} AVISO: {a}")
        return (res["prompts"][0], res["negative"], razonamiento)


NODE_CLASS_MAPPINGS = {"RafaPromptStudio": RafaPromptStudio}
NODE_DISPLAY_NAME_MAPPINGS = {"RafaPromptStudio": "Prompt Studio (Rafa)"}
