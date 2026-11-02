# -*- coding: utf-8 -*-
"""
rafa_ideas.py — Ideas (Rafa) + Elegir idea (Rafa)
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes

Para cuando no hay ni la idea vaga que pide Prompt Studio: se le pide a Claude una
tanda de ideas de escena (como se le pediria a un chat) y se elige una para la
'escena' de Prompt Studio / Prompt Studio FreeFuse. Las ideas son cortas y en
espanol: el prompt lo sigue escribiendo Prompt Studio, que sabe de triggers,
spans y de cada base.

ComfyUI no es un chat: cada Queue es una peticion suelta. Para encadenar
("mas como la 3, pero en un garaje") el nodo guarda cada tanda en un historial
(JSONL) y, si se le escribe algo en 'a_partir_de', le pasa a Claude la ultima
tanda. Con 'no_repetir' le pasa tambien los titulos ya dados para que no se repita.

Historial: <output de ComfyUI>/ideas/historial.jsonl (en el pod se espeja al
disco local con el resto de salidas), o RAFA_IDEAS_DIR si esta definida.

Cache: la clave son los inputs (no el historial), como un KSampler: mismos
inputs = no llama a la API; para otra tanda, cambia el seed.

Logica en funciones sin ComfyUI (construir_peticion, parsear_ideas, ...) para que
la reutilice la futura app.
"""

import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

try:
    from . import rafa_prompt_studio as rps
except ImportError:
    import rafa_prompt_studio as rps

LOG = "[RafaIdeas]"
NINGUNO = rps.NINGUNO
MAX_IDEAS = 20
HISTORIAL_TITULOS = 80  # titulos previos que se pasan para no repetir

# La regla del project, ampliada a espanol porque las ideas salen en espanol.
_BLOQUEO_ES_RE = re.compile(
    r"\b(j[oó]ven(es)?|chic[oa]s?|chaval(es)?|niñ[oa]s?|adolescentes?|menor(es)? de edad|juvenil(es)?|"
    r"crías?|muchach[oa]s?|imberbes?)\b", re.I)


def terminos_bloqueados(text: str) -> List[str]:
    t = text or ""
    return sorted(set(rps.terminos_bloqueados(t)) | {m.group(0).lower() for m in _BLOQUEO_ES_RE.finditer(t)})


SYSTEM_IDEAS = """You are Rafa's idea generator for adult, photorealistic, explicit image work between adult men. Rafa asks for scene ideas the way he would ask a chat; you return a batch of short, varied, inventive scene ideas that he will pick from. Another tool turns the chosen idea into the final image prompt, so you write IDEAS, not prompts: no tags, no camera jargon, no quality words ("ultra detailed", "8k", "realistic").

ABSOLUTE SAFETY RULE (non-negotiable): every person is an adult man. NEVER write "young", "younger", "youth", "teen", "boy", "joven", "chico", "chaval", "niño", "adolescente" or any variant, in any language. Use "hombre", "hombre maduro", "man", "mature man".

Adult content: explicit sex between adult men is a normal part of this work. When the NSFW level asks for it, name acts and anatomy directly, with no euphemisms and no moralising.

HOW TO WRITE EACH IDEA (in Spanish, Rafa's language):
- "titulo": 2-6 words.
- "escena": 1-3 sentences: where they are (a specific, visually rich place), what each named character wears (or that he is naked) and props, the pose or act and who does what to whom. Name the characters by their name. Concrete and visual.
- Vary between ideas: settings, light, time of day, outfits and props, positions and acts, number of characters actually in the frame, camera distance. Avoid repeating a setting or an act inside the batch.
- Do NOT describe the characters' fixed bodies or faces (build, belly, mustache, baldness, body hair, feet, age): their LoRAs give them. You may say what they DO with them (a foot on someone's belly, a hand on a mustache).
- Follow Rafa's request and his fetishes when he names them.
"""

SYSTEM_FREEFUSE = """THESE IDEAS WILL BE GENERATED WITH FREEFUSE (one LoRA per character, each one restricted to his own region of the image). So:
- Give each character his own zone of the frame (left / centre / right, foreground / background) and keep the bodies readable and distinguishable. Contact is fine (a hand, a foot, a mouth), but avoid poses where two characters' bodies merge into one mass (one lying fully on top of another, tight full-body tangles) unless Rafa asks for it.
- Extra people without a LoRA are fine; mention them as part of the place ("otros hombres en la sauna")."""


def historial_path() -> str:
    d = os.getenv("RAFA_IDEAS_DIR", "").strip()
    if not d:
        try:
            import folder_paths  # ComfyUI
            d = os.path.join(folder_paths.get_output_directory(), "ideas")
        except Exception:
            d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ideas")
    return os.path.join(d, "historial.jsonl")


def leer_historial(path: Optional[str] = None, max_tandas: int = 50) -> List[Dict[str, Any]]:
    path = path or historial_path()
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out[-max_tandas:]


def guardar_tanda(tanda: Dict[str, Any], path: Optional[str] = None) -> None:
    path = path or historial_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(tanda, ensure_ascii=False) + "\n")


def personajes_info(sel: List[str]) -> List[Dict[str, str]]:
    out = []
    for c in sel:
        if c and c != NINGUNO:
            p = rps.load_personaje(c)
            out.append({"nombre": p["trigger"], "class": p["class"]})
    return out


def construir_system(freefuse: bool, estetica: Optional[str]) -> str:
    parts = [SYSTEM_IDEAS]
    if freefuse:
        parts.append(SYSTEM_FREEFUSE)
    if estetica:
        parts.append("RAFA'S TASTE (for people without a LoRA and for the tone; never to describe a named "
                     "character's body):\n\n" + estetica)
    return ("\n\n" + "=" * 50 + "\n\n").join(parts)


def construir_peticion(peticion: str, personajes: List[Dict[str, str]], cantidad: int, nsfw: str,
                       a_partir_de: str = "", ultima: Optional[Dict[str, Any]] = None,
                       titulos_previos: Optional[List[str]] = None) -> str:
    lines = []
    if personajes:
        lines.append("CHARACTERS WITH A LoRA (use these names): " + "; ".join(
            f"{p['nombre']} ({p['class']})" if p["class"] else p["nombre"] for p in personajes)
            + ". Not every idea must use all of them unless Rafa asks.")
    lines.append(f"NSFW LEVEL: {nsfw}." + (" Explicit sex, named." if nsfw == "explicit" else
                                           " Nudity or tension, no explicit acts." if nsfw == "suggestive"
                                           else " No nudity, no sexual content."))
    if a_partir_de.strip() and ultima and ultima.get("ideas"):
        prev = "\n".join(f"{i + 1}. {x.get('titulo', '')} — {x.get('escena', '')}"
                         for i, x in enumerate(ultima["ideas"]))
        lines.append("YOUR PREVIOUS BATCH (Rafa refers to it by number):\n" + prev)
        lines.append("RAFA NOW ASKS (build on the previous batch):\n" + a_partir_de.strip())
        if peticion.strip():
            lines.append("HIS ORIGINAL REQUEST, for context:\n" + peticion.strip())
    else:
        lines.append("RAFA'S REQUEST:\n" + (peticion.strip() or a_partir_de.strip()))
    if titulos_previos:
        lines.append("ALREADY GIVEN BEFORE (do not repeat these ideas or their settings): "
                     + "; ".join(titulos_previos))
    lines.append(f"""Return EXACTLY {cantidad} ideas. Reply ONLY with valid JSON, no markdown fences:
{{"ideas": [{{"titulo": "...", "escena": "..."}}], "comentario": "one short line in Spanish (optional)"}}""")
    return "\n\n".join(lines)


def parsear_ideas(raw: str, cantidad: int) -> List[Dict[str, str]]:
    data = rps.parse_json(raw)
    ideas = data.get("ideas") if isinstance(data, dict) else None
    out = []
    for x in ideas or []:
        if isinstance(x, dict) and str(x.get("escena") or "").strip():
            out.append({"titulo": str(x.get("titulo") or "").strip(), "escena": str(x["escena"]).strip()})
        elif isinstance(x, str) and x.strip():
            out.append({"titulo": "", "escena": x.strip()})
    return out[:cantidad]


def formatear(ideas: List[Dict[str, str]]) -> str:
    return "\n\n".join(f"{i + 1}. {x['titulo']} — {x['escena']}" if x["titulo"] else f"{i + 1}. {x['escena']}"
                       for i, x in enumerate(ideas))


_ITEM_RE = re.compile(r"(?m)^\s*(\d+)[.)]\s+")


def elegir(texto: str, numero: int) -> str:
    """De la lista numerada que saca Ideas, la escena n (sin el titulo)."""
    partes = _ITEM_RE.split(texto or "")
    items = {}
    for k in range(1, len(partes) - 1, 2):
        items[int(partes[k])] = partes[k + 1].strip()
    if not items:
        raise ValueError("Elegir idea: la entrada no es una lista numerada de Ideas (Rafa).")
    if numero not in items:
        raise ValueError(f"Elegir idea: no hay idea {numero} (hay {min(items)}-{max(items)}).")
    item = items[numero]
    return item.split(" — ", 1)[1].strip() if " — " in item else item


class RafaIdeas:
    @classmethod
    def INPUT_TYPES(cls):
        pers = rps.personaje_options()
        return {
            "required": {
                "peticion": ("STRING", {"multiline": True, "default": "",
                                        "tooltip": "Lo que le pedirías a un chat: «dame 10 escenas…»"}),
                "personaje_1": (pers, {"default": NINGUNO}),
                "personaje_2": (pers, {"default": NINGUNO}),
                "personaje_3": (pers, {"default": NINGUNO}),
                "personaje_4": (pers, {"default": NINGUNO}),
                "cantidad": ("INT", {"default": 10, "min": 1, "max": MAX_IDEAS}),
                "nsfw": (rps.NSFW_LEVELS, {"default": "explicit"}),
                "para_freefuse": ("BOOLEAN", {"default": True,
                                              "tooltip": "Cada personaje en su zona y cuerpos distinguibles."}),
                "no_repetir": ("BOOLEAN", {"default": True,
                                           "tooltip": "Le pasa a Claude los títulos ya dados (historial)."}),
                "usar_estetica": ("BOOLEAN", {"default": True}),
                "creatividad": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff,
                                 "tooltip": "Fijo = caché (no llama a la API). Cámbialo para otra tanda."}),
            },
            "optional": {
                "a_partir_de": ("STRING", {"multiline": True, "default": "",
                                           "tooltip": "Para encadenar: «más como la 3, pero en un garaje». "
                                                      "Usa la última tanda del historial."}),
                "api_key": ("STRING", {"default": "", "tooltip": "Vacío = ANTHROPIC_API_KEY."}),
                "modelo_claude": ("STRING", {"default": "claude-sonnet-4-6"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("ideas", "ideas_lista")
    OUTPUT_IS_LIST = (False, True)
    FUNCTION = "generar"
    CATEGORY = "rafa"

    @classmethod
    def IS_CHANGED(cls, peticion="", personaje_1=NINGUNO, personaje_2=NINGUNO, personaje_3=NINGUNO,
                   personaje_4=NINGUNO, cantidad=10, nsfw="", para_freefuse=True, no_repetir=True,
                   usar_estetica=True, creatividad=1.0, seed=0, a_partir_de="", modelo_claude="", **kw):
        # El historial NO entra: si entrara, cada Queue volveria a llamar a la API.
        key = repr(("ideas1", peticion, personaje_1, personaje_2, personaje_3, personaje_4, int(cantidad),
                    nsfw, bool(para_freefuse), bool(no_repetir), bool(usar_estetica),
                    round(float(creatividad), 4), int(seed), a_partir_de, modelo_claude))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def generar(self, peticion, personaje_1, personaje_2, personaje_3, personaje_4, cantidad, nsfw,
                para_freefuse, no_repetir, usar_estetica, creatividad, seed, a_partir_de="", api_key="",
                modelo_claude="claude-sonnet-4-6"):
        if not (str(peticion).strip() or str(a_partir_de).strip()):
            raise ValueError("Escribe una petición (o algo en a_partir_de).")
        if rps.anthropic is None:
            raise RuntimeError("Falta el SDK anthropic (requirements.txt del repo)")
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("No hay API key: ANTHROPIC_API_KEY o el input api_key.")
        cantidad = max(1, min(MAX_IDEAS, int(cantidad)))
        pers = personajes_info([personaje_1, personaje_2, personaje_3, personaje_4])
        estetica = None
        if usar_estetica:
            raw = rps._read("estetica.md")
            if raw:
                estetica = rps.body_para_claude(rps.parse_md(raw)[1])
        hist = leer_historial()
        ultima = hist[-1] if hist else None
        titulos = []
        if no_repetir:
            for t in hist:
                titulos += [x.get("titulo") or x.get("escena", "")[:60] for x in t.get("ideas", [])]
            titulos = [t for t in titulos if t][-HISTORIAL_TITULOS:]
        system = construir_system(bool(para_freefuse), estetica)
        user = construir_peticion(peticion, pers, cantidad, nsfw, a_partir_de, ultima, titulos)
        client = rps.anthropic.Anthropic(api_key=key)
        model = (modelo_claude or "").strip() or "claude-sonnet-4-6"
        messages = [{"role": "user", "content": user}]
        ideas: List[Dict[str, str]] = []
        for intento in (1, 2):
            api_kwargs = dict(model=model, max_tokens=4096,
                              temperature=max(0.0, min(1.0, float(creatividad))),
                              system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                              messages=messages)
            try:
                msg = rps.create_with_fallback(client, api_kwargs)
            except Exception as e:
                raise RuntimeError(f"Error de la API: {e}")
            raw = rps.extract_text(msg)
            u = getattr(msg, "usage", None)
            if u is not None:
                print(f"{LOG} seed={seed} intento={intento} in:{u.input_tokens} out:{u.output_tokens} "
                      f"cache_r:{getattr(u, 'cache_read_input_tokens', 0) or 0}")
            problema = None
            try:
                ideas = parsear_ideas(raw, cantidad)
                if not ideas:
                    problema = "no ideas in the JSON"
            except Exception as e:
                problema = f"not valid JSON ({e})"
            if not problema:
                bloq = terminos_bloqueados(formatear(ideas))
                if bloq:
                    problema = "it contains forbidden terms: " + ", ".join(bloq)
            if not problema:
                break
            if intento == 2:
                raise RuntimeError(f"Ideas: respuesta no válida tras reintentar ({problema}).")
            print(f"{LOG} reintento: {problema}")
            messages = messages + [{"role": "assistant", "content": raw},
                                   {"role": "user", "content": f"Rewrite the JSON: {problema}. Every person is "
                                    "an adult man. Reply ONLY with the JSON."}]
        try:
            guardar_tanda({"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "peticion": peticion,
                           "a_partir_de": a_partir_de, "personajes": [p["nombre"] for p in pers],
                           "seed": int(seed), "ideas": ideas})
        except Exception as e:
            print(f"{LOG} no se pudo guardar el historial: {e}")
        return (formatear(ideas), [x["escena"] for x in ideas])


class RafaElegirIdea:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "ideas": ("STRING", {"forceInput": True, "tooltip": "Salida 'ideas' de Ideas (Rafa)."}),
            "numero": ("INT", {"default": 1, "min": 1, "max": MAX_IDEAS}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("escena",)
    FUNCTION = "elegir"
    CATEGORY = "rafa"

    def elegir(self, ideas, numero):
        return (elegir(ideas, int(numero)),)


NODE_CLASS_MAPPINGS = {"RafaIdeas": RafaIdeas, "RafaElegirIdea": RafaElegirIdea}
NODE_DISPLAY_NAME_MAPPINGS = {"RafaIdeas": "Ideas (Rafa)", "RafaElegirIdea": "Elegir idea (Rafa)"}
