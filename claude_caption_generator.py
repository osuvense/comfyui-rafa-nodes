"""
claude_caption_generator.py
Nodo ComfyUI para captioning de imágenes via Claude API (multimodal).
Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes

Genera captions en formato FLUX Dual, ZIT Prose, o Custom para datasets de LoRA training.
A diferencia del claude_prompt_generator.py (text-only), este nodo acepta IMAGE como input.

Lógica del system_prompt:
  - format = "FLUX Dual"  + system_prompt vacío  → usa DEFAULT_PROMPT_FLUX + modificadores
  - format = "ZIT Prose"  + system_prompt vacío  → usa DEFAULT_PROMPT_ZIT + modificadores
  - format = cualquiera   + system_prompt relleno → usa system_prompt tal cual (los modificadores
                                                     nsfw/length/subject/extra SIGUEN aplicando
                                                     al final del prompt custom)
  - format = "Custom"     + system_prompt relleno → igual que arriba, pero no hay default de fallback
  - format = "Custom"     + system_prompt vacío   → devuelve error en log, no llama a API
"""

import os
import io
import base64
import time
import anthropic
import numpy as np
from PIL import Image

# ============================================================
# SYSTEM PROMPTS POR DEFECTO
# ============================================================

DEFAULT_PROMPT_FLUX = """You are an expert image captioner generating training captions for LoRA fine-tuning of image generation models.

Generate captions in FLUX Dual format: condensed keywords block followed by full descriptive prose, all as a single text string.

OUTPUT FORMAT:
[trigger_word], [keywords]. [Prose sentences.]

KEYWORD BLOCK RULES:
- Trigger word goes first, followed by a comma
- 6-12 comma-separated descriptors: body type, clothing state, pose, camera angle, setting, key visual elements
- No articles, no verbs — just nouns and adjectives
- Ordered by visual importance

PROSE BLOCK RULES:
- 2-5 sentences of rich, specific English prose
- Begin directly with description — no preamble like "This image shows..."
- Describe only what is visible — never infer or invent details not present in the image
- Include spatial relationships, lighting quality, and setting when clearly visible
- Be explicit and clinical about body, clothing state, and anatomy — no euphemisms

GENERAL RULES:
- Output ONLY the caption text — no explanation, no preamble, no markdown
- Do not rate aesthetic quality or comment on image composition
- Do not include aspect ratio, resolution, or photography meta-commentary"""

DEFAULT_PROMPT_ZIT = """You are an expert image captioner generating training captions for LoRA fine-tuning of image generation models.

Generate captions in ZIT Prose format: direct descriptive prose only, no keyword block.

OUTPUT FORMAT:
[trigger_word]. [Prose sentences.]

RULES:
- Trigger word goes first, followed by a period, then a space, then the prose
- 3-6 sentences of rich, specific English prose
- Begin directly with description — no preamble like "This image shows..."
- Describe only what is visible — never infer or invent details not present in the image
- Include spatial relationships, lighting quality, and setting when clearly visible
- Be explicit and clinical about body, clothing state, and anatomy — no euphemisms
- Output ONLY the caption text — no explanation, no preamble, no markdown
- Do not rate aesthetic quality or comment on image composition
- Do not include aspect ratio, resolution, or photography meta-commentary"""

# ============================================================
# MODIFICADORES
# ============================================================

NSFW_MODIFIER = (
    "\n\nNSFW CONTENT: This dataset contains adult content. "
    "Describe sexual anatomy, arousal states, genital detail, and explicit acts directly and clinically. "
    "Do not skip, soften, or imply — describe what is visible explicitly."
)

LENGTH_MODIFIERS = {
    "short":  "\n\nCAPTION LENGTH: Brief. Keywords only + 1 concise prose sentence.",
    "medium": "\n\nCAPTION LENGTH: Medium. Full keyword block + 2-3 prose sentences.",
    "long":   "\n\nCAPTION LENGTH: Detailed. Full keyword block + 4-6 prose sentences covering all visible elements.",
}


# ============================================================
# NODO
# ============================================================

class ClaudeCaptionGenerator:

    CATEGORY = "rafa"
    FUNCTION = "generate_caption"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("caption", "log")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":               ("IMAGE",),
                "trigger_word":        ("STRING", {
                    "default": "MyCharacter",
                    "multiline": False,
                    "tooltip": "Trigger word del LoRA. Se antepone a cada caption automáticamente."
                }),
                "subject_description": ("STRING", {
                    "default": (
                        "Example: mature obese man, completely bald, thick gray mustache, "
                        "dense body hair on chest and arms, large protruding belly."
                    ),
                    "multiline": True,
                    "tooltip": "Descripción libre del sujeto o concepto. Claude la usa para identificar correctamente al personaje en la imagen."
                }),
                "format":              (["FLUX Dual", "ZIT Prose", "Custom"], {
                    "tooltip": (
                        "FLUX Dual: keywords condensados + prosa (formato dual encoder). "
                        "ZIT Prose: prosa directa (encoder único Qwen). "
                        "Custom: usa system_prompt tal cual, sin default."
                    )
                }),
                "nsfw":                ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Activa instrucciones explícitas de descripción de contenido adulto."
                }),
                "caption_length":      (["medium", "short", "long"], {
                    "tooltip": "Controla la extensión del caption generado."
                }),
                "model":               ("STRING", {
                    "default": "claude-sonnet-4-6",
                    "tooltip": (
                        "Model string de Anthropic. Ejemplos: claude-sonnet-4-6, claude-haiku-4-5-20251001. "
                        "Actualizar aquí cuando salgan modelos nuevos, sin tocar código."
                    )
                }),
                "temperature":         ("FLOAT", {
                    "default": 0.20,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "0.20 es el valor estable probado. Valores más altos = más variación entre captions."
                }),
            },
            "optional": {
                "extra_instructions": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Instrucciones adicionales por sesión sin tocar el system prompt. Ej: 'pay special attention to tattoo placement'."
                }),
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": (
                        "Si está vacío, usa el default del formato seleccionado. "
                        "Si está relleno, lo usa como base (los modificadores nsfw/length/subject/extra se añaden igualmente). "
                        "Con format=Custom, este campo es obligatorio."
                    )
                }),
                "image_filename": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Nombre o ruta completa de la imagen. Necesario para skip_existing y para nombrar el .txt guardado. "
                        "Conectar a la salida 'filename' de un nodo Load Image Batch."
                    )
                }),
                "output_dir": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Directorio donde guardar los .txt. Si está vacío y image_filename es una ruta completa, "
                        "guarda en el mismo directorio que la imagen."
                    )
                }),
                "save_captions": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Si False, solo muestra el caption en el nodo sin escribir .txt a disco."
                }),
                "skip_existing": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Si ya existe un .txt para esta imagen, lo salta sin gastar tokens."
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API key de Anthropic. Si está vacío, usa la variable de entorno ANTHROPIC_API_KEY."
                }),
            }
        }

    # ----------------------------------------------------------

    def generate_caption(
        self,
        image,
        trigger_word,
        subject_description,
        format,
        nsfw,
        caption_length,
        model,
        temperature,
        extra_instructions="",
        system_prompt="",
        image_filename="",
        output_dir="",
        save_captions=True,
        skip_existing=True,
        api_key="",
    ):
        logs = []
        captions = []

        batch_size = image.shape[0]  # [B, H, W, C]

        for i in range(batch_size):
            img_tensor = image[i]

            # ---- Determinar nombre base ----
            if image_filename:
                fname_raw = image_filename
                if batch_size > 1:
                    base, ext = os.path.splitext(os.path.basename(fname_raw))
                    fname_base = f"{base}_{i:04d}"
                    fname_dir  = os.path.dirname(fname_raw) if os.path.dirname(fname_raw) else ""
                else:
                    fname_base = os.path.splitext(os.path.basename(fname_raw))[0]
                    fname_dir  = os.path.dirname(fname_raw) if os.path.dirname(fname_raw) else ""
            else:
                stamp = int(time.time())
                fname_base = f"image_{stamp}_{i:04d}" if batch_size > 1 else f"image_{stamp}"
                fname_dir  = ""

            # ---- Determinar directorio de guardado ----
            if output_dir:
                save_dir = output_dir
            elif fname_dir:
                save_dir = fname_dir
            else:
                save_dir = None  # no hay dónde guardar

            txt_path = os.path.join(save_dir, fname_base + ".txt") if save_dir else None

            # ---- Skip existing ----
            if skip_existing and txt_path and os.path.exists(txt_path):
                logs.append(f"[SKIP] {fname_base}.txt — ya existe")
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        captions.append(f.read().strip())
                except Exception:
                    captions.append("")
                continue

            # ---- Validar format=Custom ----
            if format == "Custom" and not system_prompt.strip():
                msg = f"[ERROR] {fname_base} — format=Custom requiere system_prompt relleno"
                logs.append(msg)
                captions.append("")
                continue

            # ---- Convertir imagen a base64 ----
            try:
                img_b64 = self._tensor_to_base64(img_tensor)
            except Exception as e:
                logs.append(f"[ERROR] {fname_base} — fallo al codificar imagen: {e}")
                captions.append("")
                continue

            # ---- Construir system prompt ----
            sys_prompt = self._build_system_prompt(
                format, system_prompt, nsfw, caption_length,
                subject_description, extra_instructions
            )

            # ---- Construir mensaje de usuario ----
            user_text = (
                f"Generate a caption for this image. The trigger word is: {trigger_word.strip()}"
                if trigger_word.strip()
                else "Generate a caption for this image."
            )

            user_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": user_text},
            ]

            # ---- Llamada a API ----
            try:
                key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
                if not key:
                    raise ValueError("No se encontró ANTHROPIC_API_KEY (ni en el nodo ni como variable de entorno)")

                client = anthropic.Anthropic(api_key=key)
                response = client.messages.create(
                    model=model.strip(),
                    max_tokens=800,
                    temperature=temperature,
                    system=sys_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )

                caption = response.content[0].text.strip()
                tok_in  = response.usage.input_tokens
                tok_out = response.usage.output_tokens

            except Exception as e:
                logs.append(f"[ERROR] {fname_base} — API: {e}")
                captions.append("")
                continue

            # ---- Guardar .txt ----
            if save_captions and txt_path:
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(caption)
                    logs.append(f"[OK] {fname_base}.txt — in:{tok_in} out:{tok_out}")
                except Exception as e:
                    logs.append(f"[WARN] {fname_base} — caption generado pero no guardado: {e}")
            else:
                reason = "save_captions=False" if not save_captions else "sin directorio de guardado"
                logs.append(f"[OK] {fname_base} (no guardado, {reason}) — in:{tok_in} out:{tok_out}")

            captions.append(caption)

        final_caption = captions[-1] if captions else ""
        final_log     = "\n".join(logs) if logs else "[OK] Sin imágenes procesadas"

        return (final_caption, final_log)

    # ----------------------------------------------------------

    def _build_system_prompt(
        self, format, custom_prompt, nsfw, caption_length,
        subject_description, extra_instructions
    ):
        # Base
        if custom_prompt.strip():
            base = custom_prompt.strip()
        elif format == "FLUX Dual":
            base = DEFAULT_PROMPT_FLUX
        else:  # ZIT Prose o Custom sin prompt (ya validado arriba)
            base = DEFAULT_PROMPT_ZIT

        # Modificadores (siempre se añaden, independientemente del base usado)
        if nsfw:
            base += NSFW_MODIFIER

        base += LENGTH_MODIFIERS.get(caption_length, LENGTH_MODIFIERS["medium"])

        if subject_description.strip():
            base += (
                "\n\nSUBJECT CONTEXT — use this to correctly identify and describe the subject:\n"
                + subject_description.strip()
            )

        if extra_instructions.strip():
            base += (
                "\n\nSESSION-SPECIFIC INSTRUCTIONS — apply these in addition to all rules above:\n"
                + extra_instructions.strip()
            )

        return base

    # ----------------------------------------------------------

    def _tensor_to_base64(self, tensor):
        """Convierte tensor ComfyUI [H, W, C] float32 0-1 a PNG base64."""
        np_img = (tensor.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(np_img)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


# ============================================================
# REGISTRO
# ============================================================

NODE_CLASS_MAPPINGS = {
    "ClaudeCaptionGenerator": ClaudeCaptionGenerator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ClaudeCaptionGenerator": "Claude Caption Generator (Rafa)",
}
