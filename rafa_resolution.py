# -*- coding: utf-8 -*-
"""
rafa_resolution.py — Resolución (Rafa), nodo de resoluciones v2
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes
Diseno: [REF]-nodo-prompt-generator.md § 8 (knowledge del project, no en el repo).

Mismo criterio que Prompt Studio: las resoluciones viven en los perfiles de modelo
(<RAFA_PERFILES_DIR>/modelos/<id>.md, clave 'resoluciones' de la cabecera YAML),
no en el codigo. Cada entrada es [ancho, alto] o [ancho, alto, "nombre"].

El desplegable lista '<nombre del modelo> — <ancho>×<alto>[ (nombre)]' de todos los
perfiles. Al ejecutar, el ancho y el alto se leen de la propia etiqueta, no del
archivo: la salida depende solo del widget (cache de ComfyUI estable) y el nodo
funciona aunque el perfil cambie o falte en ese momento.
Orientacion: 'tal cual' respeta el perfil; 'vertical' y 'horizontal' ponen el lado
corto como ancho o como alto.

El nodo viejo (ResolutionPreset, lista fija en el codigo) no se toca: lo usan los
workflows y el bot.
"""
import re
from typing import Any, Dict, List, Tuple

try:
    from .rafa_prompt_studio import _list_ids, load_profile, SIN_PERFILES
except ImportError:  # tests, cargado fuera del paquete
    from rafa_prompt_studio import _list_ids, load_profile, SIN_PERFILES

LOG = "[RafaResolution]"
ORIENTACIONES = ["tal cual", "vertical", "horizontal"]
_LABEL_RE = re.compile(r"—\s*(\d+)×(\d+)")


def _entradas(meta: Dict[str, Any]) -> List[Tuple[int, int, str]]:
    out = []
    for r in meta.get("resoluciones") or []:
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            try:
                w, h = int(r[0]), int(r[1])
            except (TypeError, ValueError):
                continue
            nombre = str(r[2]).strip() if len(r) >= 3 and r[2] is not None else ""
            out.append((w, h, nombre))
    return out


def opciones() -> List[str]:
    opts = []
    for mid in _list_ids("modelos"):
        try:
            meta, _, _ = load_profile("modelos", mid)
        except Exception as e:
            print(f"{LOG} perfil modelos/{mid}.md ilegible: {e}")
            continue
        nombre = str(meta.get("nombre") or mid)
        for w, h, n in _entradas(meta):
            opts.append(f"{nombre} — {w}×{h}" + (f" ({n})" if n else ""))
    return opts or [SIN_PERFILES]


def parse_label(label: str) -> Tuple[int, int]:
    m = _LABEL_RE.search(label or "")
    if not m:
        raise ValueError(f"Etiqueta de resolución no reconocida: {label!r}. "
                         f"¿Hay perfiles con 'resoluciones' en modelos/?")
    return int(m.group(1)), int(m.group(2))


def orientar(w: int, h: int, orientacion: str) -> Tuple[int, int]:
    if orientacion == "vertical":
        return min(w, h), max(w, h)
    if orientacion == "horizontal":
        return max(w, h), min(w, h)
    return w, h


class RafaResolution:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        # ComfyUI vuelve a llamar a INPUT_TYPES en cada /object_info: una resolucion
        # nueva en un perfil aparece al refrescar las definiciones de nodos.
        return {
            "required": {
                "resolucion": (opciones(), {"tooltip": "De la clave 'resoluciones' de los perfiles de modelos/."}),
                "orientacion": (ORIENTACIONES, {"default": "tal cual"}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "resolver"
    CATEGORY = "rafa"

    def resolver(self, resolucion, orientacion="tal cual"):
        w, h = orientar(*parse_label(resolucion), orientacion)
        if w % 16 or h % 16:
            print(f"{LOG} aviso: {w}×{h} no es múltiplo de 16")
        return (w, h)


NODE_CLASS_MAPPINGS = {"RafaResolution": RafaResolution}
NODE_DISPLAY_NAME_MAPPINGS = {"RafaResolution": "Resolución (Rafa)"}
