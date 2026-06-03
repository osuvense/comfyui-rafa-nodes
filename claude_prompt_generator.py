# -*- coding: utf-8 -*-
"""
claude_prompt_generator.py
Meganodo de generacion de prompts via Claude API.
Parte del repo comfyui-rafa-nodes - github.com/osuvense/comfyui-rafa-nodes

Refactor paradigm-shift-aware (jun 2026). Tres ejes nuevos sobre el nodo original:

1) MODO (dropdown):
   - "LoRA solo (legacy)"        -> comportamiento original: toggles de LoRA ZIT,
                                    vocabulario aportado por la doc de cada LoRA.
                                    NO inyecta taste profile (reproduce produccion).
   - "Improvisacion sin LoRA"    -> ignora toggles; el LLM monta el prompt desde una
                                    idea vaga + el taste profile (si esta activo).
                                    Para probar modelos a pelo sin LoRA.
   - "LoRA + improvisacion"       -> triggers de LoRA + taste profile combinados.

2) MODELO DESTINO (dropdown): cambia las reglas de prompting que se le dan al LLM.
   - Z-Image Turbo  : prosa single-encoder Qwen3-4B (lo original).
   - Klein / FLUX.2 : prosa single-encoder Qwen3-8B, CFG real, usa negative.
   - FLUX.1 legacy  : DUAL encoder -> rellena clip_l + t5xxl por separado.
   - Chroma1-HD     : prosa + tags de calidad, usa negative.

3) TASTE PROFILE embebido + toggle: ADN estetico destilado de los captions de
   produccion. Activable/desactivable. Solo actua en los modos de improvisacion.

Compatibilidad: los inputs y outputs originales (ceylan/lexte/yum/scene/api_key ->
prompt/razonamiento) se conservan en su posicion. Un workflow viejo carga con
mode="LoRA solo (legacy)" y target="Z-Image Turbo" por defecto => comportamiento
identico al de antes. Los outputs clip_l/t5xxl/negative se anaden al final.

JSON obligatorio como output - mismo framing que el agente Telegram.
"""

import os
import json
import anthropic
from typing import Dict, Any, List, Tuple

# ============================================================
# RUTAS DE CAPTIONS - ajustar si es necesario
# ============================================================

CAPTIONS_BASE = os.environ.get(
    "RAFA_CAPTIONS_DIR",
    "/workspace/datasets"
)

CAPTION_FILES = {
    "ceylan": os.path.join(CAPTIONS_BASE, "claude_context_ceylan.txt"),
    "lexte":  os.path.join(CAPTIONS_BASE, "claude_context_lexte.txt"),
    "yum":    os.path.join(CAPTIONS_BASE, "claude_context_yum.txt"),
}

# ============================================================
# TASTE PROFILE EMBEBIDO - ADN estetico de Rafa
# ------------------------------------------------------------
# Destilado de los captions de produccion (Lesty/Yum/Ceylan/Ceyblan) y del
# vocabulario de inferencia consolidado en [REF]-klein-stack.md.
# NOTA: esto es para INFERENCIA (describir el lote completo), NO para captions
# de training (donde se enmascara la identidad). En inferencia sin LoRA hay que
# describir todo explicitamente porque no hay trigger que absorba la identidad.
# Solo se inyecta en los modos de improvisacion y si el toggle esta activo.
# ============================================================

TASTE_PROFILE = """## SUBJECT AESTHETIC GUIDE (apply when improvising or when the user does not fully specify the man)

Default subject: a mature, very heavy adult man (morbidly obese / superchub), roughly 45-70 years old. Photoreal, candid, unidealized real body. NEVER glamorized, athletic or slim by default.

Core features to favor unless the user explicitly says otherwise:
- BUILD: very obese, heavyset, soft. A very large, protruding belly that hangs heavily downward and overhangs; the belly is a focal element of the image.
- BODY HAIR: densely hairy - thick hair on chest, belly, arms and legs; gray/silver patterns welcome.
- HEAD / FACE: bald head OR short gray hair; a thick gray or silver mustache, very often a full thick gray beard; visible double chin.
- SKIN: light or light-brown, mature texture, natural pores; not airbrushed.
- FEET: bare feet are a recurring point of interest; when feet are in frame, render them clearly and in detail.
- EXPLICIT MALE ANATOMY (when NSFW and in frame): uncircumcised, retracted foreskin; state flaccid / semi-erect / fully erect; pubic area covered in dense dark hair.

Preferred phrasings (reuse these exact descriptors for consistency):
"mature obese bear-build man", "large round prominent belly", "large protruding belly hanging heavily downward", "large hairy overhanging belly", "hairy chest and belly", "dense gray body hair", "bald head, thick gray mustache", "full thick gray beard", "in his late sixties", "completely nude" (not just "nude").

Tone: intimate, candid, documentary realism of a real heavy mature body. If a partner/second man appears and the user does not specify him, he matches the same prototype unless told otherwise.

This is a GUIDE, not a cage: always honor explicit user choices (a slimmer partner, specific clothing, a specific setting, SFW, etc.) over these defaults."""

# ============================================================
# DOCUMENTACION DE LORAS - embebida para portabilidad (sin cambios)
# ============================================================

LORA_DOCS = {

"ceylan": """
## LoRA: CeylanV5ZIT
- Trigger word: Ceylan (siempre al inicio del prompt)
- Modelo: Z-Image Turbo (encoder Qwen3-4B, prosa directa sin separacion CLIP/T5)

### Descripcion fisica
Hombre maduro (40-50 anos), complexion muy obesa. Cabeza completamente calva (bald head).
Bigote grueso gris (thick gray mustache). Vello corporal denso en pecho, abdomen, brazos y piernas.
Barriga grande y prominente que cae hacia abajo (large protruding belly hanging heavily downward).
Piel clara o marron clara. Doble papada visible en planos cerrados.

### Vocabulario de entrenamiento (usar estas expresiones exactas)
- "his large protruding belly hanging heavily downward"
- "large, protruding belly dominates the frame"
- "heavy, obese build" / "very high level of obesity"
- "hairy chest and arms" / "dense body hair on his chest and legs"
- "bald head, thick gray mustache"
- "completely nude" (obligatorio para desnudo, no vale solo "nude")
- "shows his full body from head to feet" (para full body)
- "captured from eye level" (para angulo neutro)

### Sesgos a compensar
- 34/50 fotos son close-up → especificar "shows his full body from head to feet" si quieres full body
- Angulo bajo espontaneo → anadir "captured from eye level" si quieres angulo neutro
- Interior con puerta blanca aparece espontaneamente → especificar contexto
- "completely nude" obligatorio para desnudo

### Reglas de prompt
1. "Ceylan" al inicio, solo
2. Mencionar siempre la barriga: "his large protruding belly hanging heavily downward"
3. Estado de ropa siempre explicito
4. Angulo siempre explicito si importa
""",

"lexte": """
## LoRA: LexteV3ZIT
- Trigger word: Lexte (siempre al inicio, SIEMPRE seguido de "mature obese man, large belly")
- Modelo: Z-Image Turbo (encoder Qwen3-4B)

### REGLA CRITICA — sesgo femenino
"Lexte" tiene asociacion fonética femenina en el corpus de entrenamiento.
SIN descriptores de genero explicitos, genera mujer.
FORMATO OBLIGATORIO: "Lexte, mature obese man, large belly, [resto del prompt]"
Nunca omitir "mature obese man, large belly" despues del trigger.

### Descripcion fisica
Hombre maduro, complexion obesa/bear-build. Pelo corto gris (salt-and-pepper).
Barba gris completa y espesa (full thick gray beard). Barriga grande, overhanging belly.
Pecho y cuerpo densamente cubierto de vello corporal.
Tatuaje manga elaborado en brazo izquierdo (colorido, hasta el hombro).
Tatuaje pequeno de oso cartoon en zona lumbar (visible en poses de espalda).
Tatuaje geometrico/cristalino en pectoral derecho.

### Vocabulario de entrenamiento
- "mature obese bear-build man"
- "short gray hair and a full thick gray beard"
- "large round prominent belly" / "large hairy overhanging belly"
- "hairy chest" / "densely covered in body hair"
- "colorful tattoo sleeve on his left arm"
- "completely nude" / "shirtless"

### Reglas de prompt
1. "Lexte" al inicio, seguido INMEDIATAMENTE de "mature obese man, large belly"
2. Prosa descriptiva, no tags
3. Estado de ropa explicito
""",

"yum": """
## LoRA: YumV3ZIT
- Trigger word: Yum (siempre al inicio cuando esta activo)
- Modelo: Z-Image Turbo (encoder Qwen3-4B)
- Concepto: anatomia genital masculina (no es un personaje visual)

### Cuando usar Yum
- Primer plano genital (close-up de genitales)
- Cuando el pene es elemento principal del encuadre
- Cuando se necesita detalle anatomico especifico (ereccion, prepucio, venas, textura)

### Cuando NO usar Yum
- Poses de cuerpo completo donde los genitales no son el foco
- Retratos o planos de torso/cara
- Escenas SFW o topless

### Vocabulario de entrenamiento
- Estado: "flaccid uncircumcised penis" / "semi-erect penis" / "fully erect penis"
- Anatomia: "uncircumcised with retracted foreskin" / "prominent glans" / "visible veins"
- "large, hairy, overhanging belly" (SIEMPRE presente — elemento central del dataset)
- "pubic area covered in dense, dark brown hair"
- Agarre: "hand gripping the base with a firm, overhand grip" / "fingers wrapped around the base"
- Angulo: "close-up, top-down angle" (el mas frecuente en el dataset)

### Reglas de prompt
1. "Yum" al inicio cuando esta activo
2. Describir siempre el estado de ereccion (flaccid / semi-erect / fully erect)
3. Mencionar siempre "large overhanging belly"
4. Especificar angulo: "top-down" es el mas natural para este LoRA
""",

}

# ============================================================
# GUIAS POR MODELO DESTINO
# Cada bloque le dice al LLM como escribir el prompt para ese modelo
# y que campos de salida rellenar.
# ============================================================

MODEL_GUIDES = {

"Z-Image Turbo": """## TARGET MODEL: Z-Image Turbo
Single text encoder (Qwen3-4B). Write ONE positive prompt in natural English prose,
direct and specific, about 2-4 sentences. No keyword lists, no CLIP/T5 split.
This model does NOT use a negative prompt: leave "negative" empty.
Leave "clip_l" and "t5xxl" empty.
Trigger words of active LoRAs go at the very start, comma-separated.""",

"Klein / FLUX.2": """## TARGET MODEL: FLUX.2 Klein
Single Qwen3-8B encoder, real CFG (CFGGuider @ ~4.5). Write ONE positive prompt in
natural English prose. Recommended structure:
[character triggers if any], [scene and general context], [detailed physical
description: body type, body hair, age, baldness/hair, mustache, beard], [specific
pose and action], [lighting and atmosphere], [photographic details: angle, framing,
sharpness, skin texture].
Word ORDER matters: put the most important elements first. Ideal length ~30-80 words.
For photorealism, name a camera/lens/film stock when it fits (e.g. "shot on Fujifilm
X-T5, 35mm f/1.4"). FLUX.2 supports neither keyword spam nor reliance on negation in
the positive prompt - describe what you WANT.
ALSO produce a "negative" prompt: Klein uses real CFG so negatives work, and they are
needed to fight the SNOFS merge female bias. Sensible baseline (adapt as needed):
"girly, femenine, vagina, pussy, blurry, out of focus, duplicated arms feet or fingers,
inconsistent positions, aberrations, unreal bodies".
Leave "clip_l" and "t5xxl" empty.""",

"FLUX.1 legacy": """## TARGET MODEL: FLUX.1 legacy (DUAL ENCODER)
This model uses TWO encoders. You MUST fill two SEPARATE fields, never the same text in both:
- "clip_l": trigger words + condensed keywords only (who, clothing state, NSFW/SFW).
  Shape example: "Ceylan Lesty, completely nude male, fully erect, full body, realistic photo, NSFW".
- "t5xxl": full descriptive prose. POSITION matters (relative positional embeddings):
  put each trigger word immediately before that character's descriptive block.
  Shape: "[scene context, lighting, angle], Trigger [facial descriptors], [body
  descriptors], [genital area if relevant], [final technical details]".
ALSO produce a "negative" prompt (quality + anatomy control).
Put a readable combined version of clip_l + t5xxl in "prompt" too (only for preview);
the fields that get wired into the workflow are "clip_l" and "t5xxl".""",

"Chroma1-HD": """## TARGET MODEL: Chroma1-HD
FLUX.1-schnell based foundational model. Write ONE positive prompt in natural English
prose, detailed. It also responds to quality/aesthetic tags: you MAY append tags such
as "aesthetic 11" or media tags like "photography_(artwork)" at the end when useful.
ALSO produce a "negative" prompt. Sensible baseline:
"low quality, ugly, unfinished, out of focus, deformed, disfigure, blurry, smudged,
restricted palette, flat colors" (add the anti-female-bias terms if a man must be
guaranteed: "girly, femenine, vagina, pussy"). Guidance ~3.0.
Leave "clip_l" and "t5xxl" empty.""",

}

# Que campos espera cada modelo (para validacion/avisos)
MODEL_FLAGS = {
    "Z-Image Turbo":  {"dual": False, "negative": False},
    "Klein / FLUX.2": {"dual": False, "negative": True},
    "FLUX.1 legacy":  {"dual": True,  "negative": True},
    "Chroma1-HD":     {"dual": False, "negative": True},
}

# ============================================================
# NUCLEO COMUN DEL SYSTEM PROMPT
# ============================================================

SYSTEM_CORE = """Eres un agente experto en escribir prompts de generacion de imagen para los modelos de difusion que usa Rafa (trabajo adulto NSFW fotorrealista). Tu tarea: convertir la idea o escena del usuario - a veces muy vaga, a veces solo un par de palabras - en el o los prompt(s) optimos para el MODELO DESTINO indicado, alineados con su estetica, rellenando tu lo que el usuario no especifique.

REGLA DE SEGURIDAD ABSOLUTA (innegociable): NUNCA uses "young", "younger", "young man" ni variantes en el prompt de imagen. El sujeto es SIEMPRE un hombre adulto/maduro. Usa "man", "adult man", "mature man". Si necesitas contraste de edad o cuerpo, usa "slim adult man", nunca "young".

Contenido adulto: el contenido sexual explicito entre adultos es parte normal del trabajo; descripcion anatomica directa y clinica cuando la escena lo pida. Sin eufemismos innecesarios, sin moralizar.

REGLA DE FORMATO: responde UNICAMENTE con JSON valido. Sin texto antes ni despues. Sin markdown fences."""


def load_captions(path: str, name: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[ClaudePromptGenerator] No se pudo leer captions de {name}: {e}")
        return ""


def build_output_format(variants: int) -> str:
    """Bloque de FORMATO DE RESPUESTA del system prompt."""
    base = """FORMATO DE RESPUESTA (JSON, exactamente estas claves):
{
  "prompt": "prompt positivo principal en ingles (SIEMPRE relleno)",
  "clip_l": "solo FLUX.1 legacy; en otros modelos cadena vacia",
  "t5xxl": "solo FLUX.1 legacy; en otros modelos cadena vacia",
  "negative": "negative prompt en ingles si el modelo lo usa; si no, cadena vacia",
  "variants": [LISTA_DE_VARIANTES],
  "razonamiento": "explicacion BREVE en espanol de las decisiones tomadas"
}"""
    if variants > 1:
        base += f"""

Genera {variants} variantes DISTINTAS del prompt en el array "variants" (la primera
debe coincidir con "prompt"). Varia composicion, pose, encuadre, escenario y detalle;
manten coherente la estetica del sujeto. Para FLUX.1 legacy, cada variante es el texto
combinado de preview."""
    else:
        base += """

"variants" debe ser un array vacio []."""
    return base


# Constantes de los dropdowns
MODES = ["LoRA solo (legacy)", "Improvisacion sin LoRA", "LoRA + improvisacion"]
TARGET_MODELS = ["Z-Image Turbo", "Klein / FLUX.2", "FLUX.1 legacy", "Chroma1-HD"]
NSFW_LEVELS = ["explicit", "suggestive", "sfw"]
FRAMINGS = ["auto", "portrait", "upper body", "full body", "genital close-up"]


class ClaudePromptGenerator:
    """
    Meganodo de generacion de prompts via Claude API.
    Modo + modelo destino + taste profile + dials. Ver docstring del modulo.
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.client = None

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                # --- inputs originales (se conservan en posicion) ---
                "ceylan": (["disabled", "enabled"], {"default": "disabled"}),
                "lexte":  (["disabled", "enabled"], {"default": "disabled"}),
                "yum":    (["disabled", "enabled"], {"default": "disabled"}),
                "scene": ("STRING", {
                    "default": "Describe la escena o suelta un par de ideas vagas.",
                    "multiline": True
                }),
                # --- ejes nuevos del refactor ---
                "mode": (MODES, {
                    "default": MODES[0],
                    "tooltip": "Legacy = comportamiento original por toggles de LoRA. "
                               "Improvisacion = el LLM monta el prompt desde tu idea + taste profile. "
                               "Mixto = triggers de LoRA + taste profile."
                }),
                "target_model": (TARGET_MODELS, {
                    "default": TARGET_MODELS[0],
                    "tooltip": "Cambia las reglas de prompting. FLUX.1 legacy rellena clip_l + t5xxl."
                }),
                "taste_profile": (["enabled", "disabled"], {
                    "default": "enabled",
                    "tooltip": "Inyecta tu ADN estetico embebido. Solo actua en los modos de "
                               "improvisacion (en legacy se ignora). Desactivalo para probar el "
                               "modelo 'limpio' sin sesgar."
                }),
                "nsfw": (NSFW_LEVELS, {
                    "default": "explicit",
                    "tooltip": "explicit = sexual directo; suggestive = insinuado; sfw = sin desnudo."
                }),
                "framing": (FRAMINGS, {
                    "default": "auto",
                    "tooltip": "Plano sugerido. 'auto' = el LLM decide segun la escena."
                }),
                "variants": ("INT", {
                    "default": 1, "min": 1, "max": 6, "step": 1,
                    "tooltip": "Cuantas variantes generar de un tiro (van en el campo razonamiento)."
                }),
                "creativity": ("FLOAT", {
                    "default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Mapea a temperature. Bajo = fiel/estable; alto = improvisa mas."
                }),
                "seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xffffffffffffffff,
                    "tooltip": "Cache buster. Fijo + sin otros cambios = usa cache, NO gasta tokens. "
                               "Sube el seed (o ponlo en randomize/increment) para forzar una variante nueva."
                }),
            },
            "optional": {
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "claude_model": ("STRING", {
                    "default": "claude-sonnet-4-6",
                    "multiline": False,
                    "tooltip": "Modelo de Claude. Sonnet 4.6 por defecto."
                }),
                "extra_directives": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Instrucciones extra ad-hoc para esta generacion."
                }),
                "taste_profile_override": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Si no esta vacio, sustituye al taste profile embebido (sigue en codigo, "
                               "esto es solo un override puntual in-canvas)."
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "razonamiento", "clip_l", "t5xxl", "negative")
    FUNCTION = "generate_prompt"
    CATEGORY = "rafa"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, scene="", mode="", target_model="", taste_profile="",
                   ceylan="", lexte="", yum="", nsfw="", framing="",
                   variants=1, creativity=0.8, seed=0, claude_model="",
                   extra_directives="", taste_profile_override="", **kwargs):
        # Clave determinista de los inputs: el nodo solo se re-ejecuta (y gasta
        # tokens en la API) cuando cambia alguno. Repetir Queue con todo igual usa
        # la cache de ComfyUI y NO vuelve a llamar. Para forzar una variante nueva
        # sin tocar la escena, sube 'seed' (o ponlo en randomize/increment), igual
        # que el seed de un KSampler. api_key se excluye a proposito.
        import hashlib
        key = repr((scene, mode, target_model, taste_profile, ceylan, lexte, yum,
                    nsfw, framing, int(variants), round(float(creativity), 4),
                    int(seed), claude_model, extra_directives, taste_profile_override))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _build_system_prompt(
        self,
        mode: str,
        target_model: str,
        active: Dict[str, bool],
        use_taste: bool,
        nsfw: str,
        framing: str,
        variants: int,
        extra_directives: str,
        taste_text: str,
    ) -> str:
        parts: List[str] = [SYSTEM_CORE.strip()]

        # 1) Guia del modelo destino
        parts.append(MODEL_GUIDES[target_model].strip())

        # 2) Taste profile (solo en modos de improvisacion)
        improvising = mode in (MODES[1], MODES[2])
        if improvising and use_taste and taste_text.strip():
            parts.append("## YOUR AESTHETIC (default taste, apply unless overridden)\n"
                         + taste_text.strip())

        # 3) Dials: NSFW + framing
        nsfw_map = {
            "explicit": "NSFW level: EXPLICIT. Explicit adult sexual content and direct "
                        "anatomical description are expected when the scene calls for it.",
            "suggestive": "NSFW level: SUGGESTIVE. Sensual/implied, nudity partial or "
                          "teased, no explicit genital action.",
            "sfw": "NSFW level: SFW. No nudity, no sexual content. Clothed scene.",
        }
        parts.append(nsfw_map[nsfw])
        if framing != "auto":
            parts.append(f"Preferred framing/shot: {framing}. Reflect it in the prompt.")

        # 4) LoRAs activos (en legacy y mixto)
        using_loras = mode in (MODES[0], MODES[2])
        if using_loras and any(active.values()):
            parts.append("## ACTIVE LoRAs AND THEIR DOCUMENTATION")
            for name, enabled in active.items():
                if not enabled:
                    continue
                section = LORA_DOCS[name].strip()
                captions = load_captions(CAPTION_FILES[name], name)
                if captions:
                    section += ("\n\n### Captions de entrenamiento (vocabulario exacto del modelo):\n"
                                + captions)
                parts.append(section)
        elif using_loras and not any(active.values()) and mode == MODES[0]:
            # Legacy sin loras activos: comportamiento original (prompt generico)
            parts.append("No hay LoRAs activos. Genera un prompt generico basado en la escena.")

        # 5) Instrucciones extra ad-hoc
        if extra_directives.strip():
            parts.append("## INSTRUCCIONES EXTRA DE ESTA GENERACION\n" + extra_directives.strip())

        # 6) Formato de salida
        parts.append(build_output_format(variants))

        return ("\n\n" + "=" * 50 + "\n\n").join(parts)

    def generate_prompt(
        self,
        ceylan: str,
        lexte: str,
        yum: str,
        scene: str,
        mode: str,
        target_model: str,
        taste_profile: str,
        nsfw: str,
        framing: str,
        variants: int,
        creativity: float,
        seed: int = 0,
        api_key: str = "",
        claude_model: str = "claude-sonnet-4-6",
        extra_directives: str = "",
        taste_profile_override: str = "",
    ) -> dict:

        if not scene.strip():
            raise ValueError("scene no puede estar vacio")

        key_to_use = api_key if api_key else self.api_key
        if not key_to_use:
            raise ValueError("No hay API key. Configura ANTHROPIC_API_KEY o pegala en el nodo.")

        if not self.client or api_key:
            self.client = anthropic.Anthropic(api_key=key_to_use)

        active = {
            "ceylan": ceylan == "enabled",
            "lexte":  lexte  == "enabled",
            "yum":    yum    == "enabled",
        }

        use_taste = taste_profile == "enabled"
        taste_text = taste_profile_override if taste_profile_override.strip() else TASTE_PROFILE

        full_system = self._build_system_prompt(
            mode=mode,
            target_model=target_model,
            active=active,
            use_taste=use_taste,
            nsfw=nsfw,
            framing=framing,
            variants=max(1, int(variants)),
            extra_directives=extra_directives,
            taste_text=taste_text,
        )

        # creativity (0-1) -> temperature
        temperature = max(0.0, min(1.0, float(creativity)))

        try:
            message = self.client.messages.create(
                model=claude_model.strip() or "claude-sonnet-4-6",
                max_tokens=2048,
                temperature=temperature,
                system=full_system,
                messages=[{"role": "user", "content": scene}]
            )

            if not message.content:
                raise RuntimeError("La API no devolvio contenido")

            raw = message.content[0].text.strip()
            print(f"[ClaudePromptGenerator] mode={mode} model={target_model} seed={seed} Raw: {repr(raw[:200])}")

            # Strip markdown fences si Claude las incluye
            if raw.startswith("```"):
                raw = raw.strip("`\n ")
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"[ClaudePromptGenerator] JSON parse error: {e}")
                return {
                    "ui": {"prompt": [raw], "razonamiento": ["Error al parsear JSON"]},
                    "result": (raw, "Error al parsear JSON", "", "", "")
                }

            prompt = (data.get("prompt") or "").strip()
            clip_l = (data.get("clip_l") or "").strip()
            t5xxl = (data.get("t5xxl") or "").strip()
            negative = (data.get("negative") or "").strip()
            razonamiento = (data.get("razonamiento") or "").strip()
            var_list = data.get("variants") or []
            if not isinstance(var_list, list):
                var_list = []

            # Fallbacks de coherencia
            if not prompt and clip_l:
                prompt = (clip_l + "\n\n" + t5xxl).strip()
            if not prompt and var_list:
                prompt = str(var_list[0]).strip()
            if not prompt:
                raise ValueError("Campo 'prompt' vacio en JSON")

            # Razonamiento enriquecido para inspeccion en el nodo
            extra_view = []
            if negative:
                extra_view.append("NEGATIVE:\n" + negative)
            if clip_l or t5xxl:
                extra_view.append("CLIP_L:\n" + clip_l + "\n\nT5XXL:\n" + t5xxl)
            if len(var_list) > 1:
                vv = "\n\n".join(f"[{i+1}] {str(v).strip()}" for i, v in enumerate(var_list))
                extra_view.append("VARIANTES:\n" + vv)
            razonamiento_full = razonamiento
            if extra_view:
                razonamiento_full = (razonamiento + "\n\n" + ("\n\n----\n\n".join(extra_view))).strip()

            return {
                "ui": {"prompt": [prompt], "razonamiento": [razonamiento_full]},
                "result": (prompt, razonamiento_full, clip_l, t5xxl, negative)
            }

        except anthropic.APIConnectionError as e:
            raise RuntimeError(f"Connection error: {str(e)}")
        except anthropic.RateLimitError as e:
            raise RuntimeError(f"Rate limit: {str(e)}")
        except anthropic.APIError as e:
            raise RuntimeError(f"API Error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Error inesperado: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "ClaudePromptGenerator": ClaudePromptGenerator
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ClaudePromptGenerator": "Claude Prompt Generator (Rafa)"
}
