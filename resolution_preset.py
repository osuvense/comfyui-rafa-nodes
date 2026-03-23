# resolution_preset.py
# Nodo ComfyUI: selector de resoluciones predefinidas con orientación vertical/horizontal
# Parte del repo rafa-node-resize — github.com/osuvense/rafa-node-resize

# Presets definidos en su versión PORTRAIT (retrato / vertical)
# Orientación "Horizontal" invierte W y H automáticamente
# Presets cuadrados producen el mismo resultado en ambas orientaciones

PRESETS = {
    "FLUX — Retrato (1024×1024)":        (1024, 1024),
    "FLUX — Cuerpo entero (832×1216)":   ( 832, 1216),
    "WAN — 480p (480×832)":              ( 480,  832),
    "WAN — 720p (720×1280)":             ( 720, 1280),
    "WAN — Cuadrado (1024×1024)":        (1024, 1024),
}


class ResolutionPreset:
    """
    Selector de resoluciones estándar para FLUX y WAN.
    Outputs: width (INT) y height (INT), listos para conectar a cualquier nodo.
    Orientación Vertical = retrato (H > W). Horizontal = paisaje (W > H).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "preset":       (list(PRESETS.keys()),),
                "orientacion":  (["Vertical", "Horizontal"],),
            }
        }

    RETURN_TYPES  = ("INT", "INT")
    RETURN_NAMES  = ("width", "height")
    FUNCTION      = "get_resolution"
    CATEGORY      = "rafa"
    OUTPUT_NODE   = False

    def get_resolution(self, preset, orientacion):
        w, h = PRESETS[preset]
        if orientacion == "Horizontal":
            # Si ya es apaisado o cuadrado, no cambia nada
            return (max(w, h), min(w, h))
        else:
            # Vertical: el lado corto es el ancho
            return (min(w, h), max(w, h))


NODE_CLASS_MAPPINGS = {
    "RafaResolutionPreset": ResolutionPreset,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RafaResolutionPreset": "Resolución Preset (Rafa)",
}
