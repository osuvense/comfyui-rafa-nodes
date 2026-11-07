# -*- coding: utf-8 -*-
"""
rafa_receta.py — la «receta» de una imagen (de donde salio y con que intencion)
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes

Para animar una imagen que ya gusta hace falta saber como se hizo: la escena que
pidio Rafa (la intencion), el prompt final, los personajes, la base y el seed.

El PNG que guarda ComfyUI lleva el grafo (chunk 'prompt'), pero si el prompt lo
escribio Prompt Studio el grafo solo tiene sus INPUTS (la escena, los personajes...),
no el texto que devolvio Claude. Por eso:
  1. Prompt Studio y Prompt Studio FreeFuse registran cada prompt que generan en
     <output de ComfyUI>/recetas/prompt_studio.jsonl (o RAFA_RECETAS_DIR), con una
     clave calculada de sus inputs (sin api_key y sin el contenido de los perfiles).
  2. Al leer un PNG, se busca en el grafo el nodo de Prompt Studio, se recalcula la
     clave y se recupera el prompt del registro. Si no esta (imagen anterior al
     registro), queda la escena, que es la intencion, y el texto literal que haya
     en los CLIPTextEncode del grafo.

Todo en funciones sin ComfyUI: la futura app las importa tal cual.
"""

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

LOG = "[RafaReceta]"

STUDIO_CLASSES = ("RafaPromptStudio", "RafaPromptStudioFreeFuse")
# Inputs que forman la clave (los mismos para los dos Studios; los que no existan se ignoran)
CLAVE_CAMPOS = ("escena", "base", "lexico", "personaje_1", "personaje_2", "personaje_3", "personaje_4",
                "usar_estetica", "nsfw", "encuadre", "estilo", "variantes", "creatividad", "seed",
                "modelo_claude", "extra", "nombrar_rasgos_fijos", "reparto")
TEXT_ENCODERS = ("CLIPTextEncode", "CLIPTextEncodeFlux", "TextEncodeQwenImageEdit", "CLIPTextEncodeSDXL")
LORA_LOADERS = ("LoraLoader", "LoraLoaderModelOnly")


# ============================================================
# Registro de Prompt Studio
# ============================================================

def recetas_dir() -> str:
    d = os.getenv("RAFA_RECETAS_DIR", "").strip()
    if d:
        return d
    try:
        import folder_paths  # ComfyUI
        return os.path.join(folder_paths.get_output_directory(), "recetas")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "_recetas")


def registro_path() -> str:
    return os.path.join(recetas_dir(), "prompt_studio.jsonl")


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return round(v, 4)
    return v


def clave_studio(inputs: Dict[str, Any]) -> str:
    """Clave estable de una llamada a Prompt Studio a partir de sus inputs de widget."""
    d = {k: _norm(inputs[k]) for k in CLAVE_CAMPOS if k in inputs and not isinstance(inputs[k], list)}
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


def registrar_studio(nodo: str, inputs: Dict[str, Any], prompt: str, negative: str,
                     extra: Optional[Dict[str, Any]] = None, path: Optional[str] = None) -> Optional[str]:
    """Anade una linea al registro. Nunca lanza: un fallo aqui no puede romper la generacion."""
    try:
        path = path or registro_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        limpio = {k: v for k, v in inputs.items() if k in CLAVE_CAMPOS}
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "nodo": nodo, "clave": clave_studio(inputs),
               "inputs": limpio, "prompt": prompt, "negative": negative}
        if inputs.get("personajes_reparto"):
            rec["personajes"] = list(inputs["personajes_reparto"])
        if extra:
            rec.update(extra)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec["clave"]
    except Exception as e:  # pragma: no cover
        print(f"{LOG} no se pudo registrar la receta: {e}")
        return None


def buscar_studio(inputs: Dict[str, Any], path: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], int]:
    """Registros cuyos inputs coinciden con los LITERALES del grafo (un input enlazado, p. ej. la
    escena que llega de Elegir idea, no esta en el grafo y no se compara). Devuelve el mas
    reciente y cuantos coinciden (>1 = ambiguo)."""
    path = path or registro_path()
    if not os.path.isfile(path):
        return None, 0
    lit = {k: _norm(v) for k, v in inputs.items() if k in CLAVE_CAMPOS and not isinstance(v, list)}
    if not lit:
        return None, 0
    exacta = clave_studio(inputs) if len(lit) == len([k for k in inputs if k in CLAVE_CAMPOS]) else None
    hallado, n = None, 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if exacta and rec.get("clave") == exacta:
                hallado, n = rec, 1  # la clave exacta manda
                continue
            if exacta:
                continue
            ri = rec.get("inputs") or {}
            if all(_norm(ri.get(k)) == v for k, v in lit.items()):
                hallado, n = rec, n + 1
    return hallado, n


# ============================================================
# Lectura del PNG
# ============================================================

def leer_info_png(path: str) -> Dict[str, str]:
    """Chunks de texto del PNG (prompt, workflow, rafa_receta...)."""
    from PIL import Image
    with Image.open(path) as im:
        info = dict(getattr(im, "text", {}) or {})
        for k, v in (im.info or {}).items():
            if isinstance(v, str) and k not in info:
                info[k] = v
    return info


def _resolver_literal(grafo: Dict[str, Any], valor: Any, prof: int = 0) -> Optional[str]:
    """Un input de texto puede ser literal o un enlace [id, salida] a un nodo de texto simple."""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, list) and len(valor) == 2 and prof < 4:
        nodo = grafo.get(str(valor[0])) or {}
        ins = nodo.get("inputs") or {}
        for k in ("text", "string", "value", "prompt"):
            if k in ins:
                return _resolver_literal(grafo, ins[k], prof + 1)
    return None


def ideas_path() -> str:
    d = os.getenv("RAFA_IDEAS_DIR", "").strip()
    if d:
        return os.path.join(d, "historial.jsonl")
    try:
        import folder_paths  # ComfyUI
        return os.path.join(folder_paths.get_output_directory(), "ideas", "historial.jsonl")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ideas", "historial.jsonl")


def escena_desde_ideas(grafo: Dict[str, Any], enlace: Any, path: Optional[str] = None) -> Tuple[str, str]:
    """Si la escena de Studio llega de Elegir idea <- Ideas, recupera del historial de Ideas la
    escena elegida (peticion + seed de Ideas y el numero de Elegir idea). Devuelve (escena, aviso)."""
    if not (isinstance(enlace, list) and len(enlace) == 2):
        return "", ""
    eleg = grafo.get(str(enlace[0])) or {}
    if eleg.get("class_type") != "RafaElegirIdea":
        return "", ""
    ei = eleg.get("inputs") or {}
    num, link = ei.get("numero"), ei.get("ideas")
    ideas_n = grafo.get(str(link[0])) if isinstance(link, list) else None
    if not isinstance(num, int) or not ideas_n or ideas_n.get("class_type") != "RafaIdeas":
        return "", "Escena enlazada a Elegir idea, pero no se pudo seguir hasta Ideas."
    ii = ideas_n.get("inputs") or {}
    pet, seed = ii.get("peticion"), ii.get("seed")
    path = path or ideas_path()
    if not isinstance(pet, str) or not os.path.isfile(path):
        return "", "No esta el historial de Ideas para recuperar la escena."
    hallada, n = None, 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                t = json.loads(line)
            except Exception:
                continue
            if t.get("peticion") == pet and (seed is None or t.get("seed") == seed):
                hallada, n = t, n + 1
    if not hallada:
        return "", "La tanda de Ideas de esta imagen no esta en el historial."
    ideas = hallada.get("ideas") or []
    if not (1 <= num <= len(ideas)):
        return "", f"Elegir idea pide la {num}, pero la tanda tiene {len(ideas)}."
    av = f"Escena recuperada del historial de Ideas (idea {num})." + (
        f" {n} tandas con la misma peticion y seed: se usa la mas reciente." if n > 1 else "")
    return str(ideas[num - 1].get("escena") or ""), av


def reparto_del_grafo(grafo: Dict[str, Any], enlace: Any) -> List[str]:
    """Personajes de RafaRepartoFreeFuse si la entrada 'reparto' de Studio esta enlazada a el."""
    if not (isinstance(enlace, list) and len(enlace) == 2):
        return []
    n = grafo.get(str(enlace[0])) or {}
    if n.get("class_type") != "RafaRepartoFreeFuse":
        return []
    ins = n.get("inputs") or {}
    return [ins[f"personaje_{i}"] for i in range(1, 5)
            if isinstance(ins.get(f"personaje_{i}"), str) and ins[f"personaje_{i}"] != "ninguno"]


def extraer_receta(info: Dict[str, str], registro: Optional[str] = None) -> Dict[str, Any]:
    """Receta a partir de los chunks del PNG. Campos: origen, escena, prompt, negative,
    personajes, base, seed, loras, avisos."""
    rec: Dict[str, Any] = {"origen": "ninguno", "escena": "", "prompt": "", "negative": "",
                           "personajes": [], "base": "", "seed": None, "loras": [], "avisos": []}
    # 1) receta explicita (la escribira la app)
    if info.get("rafa_receta"):
        try:
            r = json.loads(info["rafa_receta"])
            if isinstance(r, dict):
                rec.update({k: v for k, v in r.items() if k != "avisos"})
                rec["origen"] = "receta"
                return rec
        except Exception:
            rec["avisos"].append("El chunk rafa_receta no es JSON valido.")
    try:
        grafo = json.loads(info.get("prompt") or "{}")
    except Exception:
        grafo = {}
        rec["avisos"].append("El PNG no trae un grafo legible (chunk 'prompt').")
    if not isinstance(grafo, dict) or not grafo:
        if not rec["avisos"]:
            rec["avisos"].append("El PNG no trae metadatos de ComfyUI.")
        return rec

    # 2) LoRAs y semilla de los samplers
    for nid, n in grafo.items():
        ct = n.get("class_type", "")
        ins = n.get("inputs") or {}
        if ct in LORA_LOADERS and isinstance(ins.get("lora_name"), str):
            rec["loras"].append({"lora": ins["lora_name"],
                                 "fuerza": ins.get("strength_model", ins.get("strength"))})
        if rec["seed"] is None:
            for k in ("seed", "noise_seed"):
                if isinstance(ins.get(k), int) and ct not in STUDIO_CLASSES:
                    rec["seed"] = ins[k]

    # 3) Prompt Studio
    studio = [(nid, n) for nid, n in grafo.items() if n.get("class_type") in STUDIO_CLASSES]
    if studio:
        nid, n = studio[0]
        ins = n.get("inputs") or {}
        if len(studio) > 1:
            rec["avisos"].append(f"Hay {len(studio)} nodos de Prompt Studio; se usa el {nid}.")
        rec["origen"] = "studio"
        rec["escena"] = ins.get("escena") if isinstance(ins.get("escena"), str) else ""
        rec["base"] = ins.get("base", "") if isinstance(ins.get("base"), str) else ""
        rec["personajes"] = [ins[k] for k in ("personaje_1", "personaje_2", "personaje_3", "personaje_4")
                             if isinstance(ins.get(k), str) and ins[k] != "ninguno"]
        rep = reparto_del_grafo(grafo, ins.get("reparto"))
        if rep:
            rec["personajes"] = rep
        hit, n = buscar_studio(ins, registro)
        if hit and n > 1:
            rec["avisos"].append(f"{n} registros encajan con esta imagen (un input enlazado no esta en el "
                                 "grafo): se usa el mas reciente. Revisa la escena.")
        if hit:
            if not rec["escena"]:
                rec["escena"] = (hit.get("inputs") or {}).get("escena", "")
            if hit.get("personajes"):
                rec["personajes"] = list(hit["personajes"])
            rec["prompt"] = hit.get("prompt", "")
            rec["negative"] = hit.get("negative", "")
            rec["origen"] = "studio+registro"
        else:
            rec["avisos"].append("Prompt Studio sin registro para esta imagen (anterior al registro o "
                                 "generada en otro pod): se usa la escena como intencion.")
        if not rec["escena"]:
            esc, av = escena_desde_ideas(grafo, ins.get("escena"))
            rec["escena"] = esc
            if av:
                rec["avisos"].append(av)

    # 4) Texto literal en los encoders (imagenes sin Studio, o prompt editado a mano)
    if not rec["prompt"]:
        textos = []
        for nid, n in grafo.items():
            if n.get("class_type") in TEXT_ENCODERS:
                ins = n.get("inputs") or {}
                for k in ("text", "prompt", "t5xxl", "clip_l"):
                    t = _resolver_literal(grafo, ins.get(k))
                    if t and t.strip():
                        textos.append(t.strip())
        if textos:
            textos.sort(key=len, reverse=True)
            rec["prompt"] = textos[0]
            if rec["origen"] == "ninguno":
                rec["origen"] = "grafo"
    if rec["origen"] == "ninguno":
        rec["avisos"].append("No se encontro ni Prompt Studio ni texto en el grafo.")
    return rec


def receta_de_png(path: str, registro: Optional[str] = None) -> Dict[str, Any]:
    rec = extraer_receta(leer_info_png(path), registro)
    rec["archivo"] = os.path.basename(path)
    return rec
