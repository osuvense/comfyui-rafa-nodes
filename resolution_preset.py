class ResolutionPreset:
    """
    Nodo de presets de resolución para diferentes modelos.
    Outputs: width (INT) + height (INT)
    """

    PRESETS = {
        # --- FLUX ---
        "FLUX — Retrato (1024×1024)": (1024, 1024),
        "FLUX — Cuerpo entero (832×1216)": (832, 1216),
        # --- ZIT 1024 ---
        "ZIT — Retrato (1024×1024)": (1024, 1024),
        "ZIT — Cuerpo entero (832×1248)": (832, 1248),
        # --- ZIT 1536 ---
        "ZIT 1536 — Retrato (1536×1536)": (1536, 1536),
        "ZIT 1536 — Cuerpo entero (1248×1872)": (1248, 1872),
        # --- WAN ---
        "WAN — 480p (480×832)": (480, 832),
        "WAN — 720p (720×1280)": (720, 1280),
        "WAN — Cuadrado (1024×1024)": (1024, 1024),
    }

    ORIENTATIONS = ["Vertical", "Horizontal"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "preset": (list(cls.PRESETS.keys()),),
                "orientacion": (cls.ORIENTATIONS, {"default": "Vertical"}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "get_resolution"
    CATEGORY = "rafa"

    def get_resolution(self, preset, orientacion):
        w, h = self.PRESETS[preset]

        if orientacion == "Vertical":
            # Vertical: el lado corto es el ancho
            return (min(w, h), max(w, h))
        else:
            # Horizontal: el lado largo es el ancho
            return (max(w, h), min(w, h))


NODE_CLASS_MAPPINGS = {
    "ResolutionPreset": ResolutionPreset
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ResolutionPreset": "Resolución Preset (Rafa)"
}
