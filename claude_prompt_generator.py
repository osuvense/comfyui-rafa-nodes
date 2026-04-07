"""
claude_prompt_generator.py
Nodo ComfyUI para generacion de prompts via Claude API.
Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes

Arquitectura:
- Toggles por personaje controlan que contexto se carga
- Documentacion de LoRAs embebida en el nodo (portable, sin dependencias externas)
- Captions de entrenamiento cargados desde disco (rutas configurables)
- Claude decide que trigger words usar segun la escena descrita
- JSON obligatorio como output — mismo framing que el agente Telegram
"""

import os
import json
import anthropic
from typing import Dict, Any

# ============================================================
# RUTAS DE CAPTIONS — ajustar si es necesario
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
# DOCUMENTACION DE LORAS — embebida para portabilidad
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
# SYSTEM PROMPT BASE
# ============================================================

SYSTEM_PROMPT_BASE = """Eres un agente especializado en configurar el text encoder de un workflow de ComfyUI con Z-Image Turbo (encoder unico Qwen3-4B).

Analiza la descripcion de escena del usuario y genera el prompt optimo para el encoder.

REGLA ABSOLUTA: responde UNICAMENTE con JSON valido. Sin texto antes ni despues. Sin markdown fences.

FORMATO DE RESPUESTA:
{
  "prompt": "texto completo para el encoder en prosa descriptiva en ingles",
  "razonamiento": "explicacion breve en espanol de las decisiones tomadas"
}

REGLAS DEL PROMPT:
- Prosa natural en ingles, 2-4 oraciones directas y especificas.
- Usa el vocabulario exacto documentado para cada LoRA activo.
- Los trigger words de los LoRAs activos van al inicio, separados por coma si hay varios.
- Nunca uses "young", "younger" ni "young man". Usa "slim adult man" si necesitas contraste de edad.
- Describe el comportamiento fisico de la masa corporal ("his belly hangs heavily", "belly presses against").
- Usa lenguaje anatomico directo para partes del cuerpo y acciones segun requiera la escena.
- IMPORTANTE para Lexte: su trigger SIEMPRE va seguido de "mature obese man, large belly" — sin esto genera mujer.
- IMPORTANTE para Yum: activar su trigger cuando la escena requiera primer plano genital o detalle anatomico.

LORAS ACTIVOS Y SU DOCUMENTACION:
"""


def load_captions(path: str, name: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[ClaudePromptGenerator] No se pudo leer captions de {name}: {e}")
        return ""


class ClaudePromptGenerator:
    """
    Genera prompts para Z-Image Turbo usando Claude API.
    Activa/desactiva personajes con toggles — Claude decide los trigger words segun la escena.
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.client = None

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "ceylan": (["disabled", "enabled"], {"default": "disabled"}),
                "lexte":  (["disabled", "enabled"], {"default": "disabled"}),
                "yum":    (["disabled", "enabled"], {"default": "disabled"}),
                "scene": ("STRING", {
                    "default": "Describe la escena que quieres generar.",
                    "multiline": True
                }),
            },
            "optional": {
                "api_key": ("STRING", {
                    "default": "",
                    "multiline": False
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "razonamiento")
    FUNCTION = "generate_prompt"
    CATEGORY = "rafa"
    OUTPUT_NODE = True

    def generate_prompt(
        self,
        ceylan: str,
        lexte: str,
        yum: str,
        scene: str,
        api_key: str = ""
    ) -> dict:

        if not scene.strip():
            raise ValueError("scene no puede estar vacio")

        key_to_use = api_key if api_key else self.api_key
        if not key_to_use:
            raise ValueError("No hay API key. Configura ANTHROPIC_API_KEY o pégala en el nodo.")

        if not self.client or api_key:
            self.client = anthropic.Anthropic(api_key=key_to_use)

        active = {
            "ceylan": ceylan == "enabled",
            "lexte":  lexte  == "enabled",
            "yum":    yum    == "enabled",
        }

        # System prompt: base + doc embebida + captions de disco para cada LoRA activo
        full_system = SYSTEM_PROMPT_BASE.strip()

        for name, enabled in active.items():
            if enabled:
                section = f"\n\n{'='*50}\n{LORA_DOCS[name].strip()}"
                captions = load_captions(CAPTION_FILES[name], name)
                if captions:
                    section += f"\n\n### Captions de entrenamiento (vocabulario exacto del modelo):\n{captions}"
                full_system += section

        if not any(active.values()):
            full_system += "\n\nNo hay LoRAs activos. Genera un prompt generico basado en la escena."

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=0.8,
                system=full_system,
                messages=[{"role": "user", "content": scene}]
            )

            if not message.content:
                raise RuntimeError("La API no devolvio contenido")

            raw = message.content[0].text.strip()
            print(f"[ClaudePromptGenerator] Raw: {repr(raw[:200])}")

            # Strip markdown fences si Claude las incluye
            if raw.startswith("```"):
                raw = raw.strip("`\n ")
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            try:
                data = json.loads(raw)
                prompt = data.get("prompt", "").strip()
                razonamiento = data.get("razonamiento", "").strip()
                if not prompt:
                    raise ValueError("Campo 'prompt' vacio en JSON")
                return {
                    "ui": {"prompt": [prompt], "razonamiento": [razonamiento]},
                    "result": (prompt, razonamiento)
                }
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[ClaudePromptGenerator] JSON parse error: {e}")
                return {
                    "ui": {"prompt": [raw], "razonamiento": ["Error al parsear JSON"]},
                    "result": (raw, "Error al parsear JSON")
                }

        except anthropic.APIError as e:
            raise RuntimeError(f"API Error: {str(e)}")
        except anthropic.RateLimitError as e:
            raise RuntimeError(f"Rate limit: {str(e)}")
        except anthropic.APIConnectionError as e:
            raise RuntimeError(f"Connection error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Error inesperado: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "ClaudePromptGenerator": ClaudePromptGenerator
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ClaudePromptGenerator": "Claude Prompt Generator (Rafa)"
}
