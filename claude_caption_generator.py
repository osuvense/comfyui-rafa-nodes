"""
claude_caption_generator.py
Nodo ComfyUI para captioning de imágenes via Claude API (multimodal).
Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes

Recibe una ruta de carpeta como input. Itera internamente sobre todas las imágenes,
gestiona skip_existing por nombre de archivo, y guarda los .txt en la misma carpeta
(o en output_dir si se especifica). Sin dependencias de nodos externos.

Lógica del system_prompt:
  - format = "FLUX Dual"  + system_prompt vacío  → usa DEFAULT_PROMPT_FLUX + modificadores
  - format = "ZIT Prose"  + system_prompt vacío  → usa DEFAULT_PROMPT_ZIT + modificadores
  - format = cualquiera   + system_prompt relleno → usa system_prompt como base + modificadores
  - format = "Custom"     + system_prompt vacío   → error en log, no llama a API
"""

import os
import io
import base64
import anthropic
from PIL import Image

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

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
    FUNCTION = "generate_captions"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("last_caption", "log")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_folder": ("STRING", {
                    "default": "/workspace/datasets/MiPersonaje/raw",
                    "multiline": False,
                    "tooltip": "Ruta de la carpeta con las imágenes. Se procesan jpg, jpeg, png, webp, bmp."
                }),
                "trigger_word": ("STRING", {
                    "default": "MyCharacter",
                    "multiline": False,
                    "tooltip": "Trigger word del LoRA. Se antepone a cada caption automáticamente."
                }),
                "subject_description": ("STRING", {
                    "default": "Describe aquí el sujeto: tipo de cuerpo, rasgos físicos clave, características identificativas...",
                    "multiline": True,
                    "tooltip": "Descripción libre del sujeto o concepto. Claude la usa para identificar correctamente al personaje en cada imagen."
                }),
                "format": (["FLUX Dual", "ZIT Prose", "Custom"], {
                    "tooltip": (
                        "FLUX Dual: keywords condensados + prosa (formato dual encoder CLIP-L / T5XXL). "
                        "ZIT Prose: prosa directa (encoder único Qwen). "
                        "Custom: usa system_prompt tal cual, sin default de fallback."
                    )
                }),
                "nsfw": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Activa instrucciones explícitas de descripción de contenido adulto."
                }),
                "caption_length": (["medium", "short", "long"], {
                    "tooltip": "Controla la extensión del caption generado."
                }),
                "model": ("STRING", {
                    "default": "claude-sonnet-4-6",
                    "tooltip": (
                        "Model string de Anthropic. Ejemplos: claude-sonnet-4-6, claude-haiku-4-5-20251001. "
                        "Editable directamente — actualizar aquí cuando salgan modelos nuevos."
                    )
                }),
                "temperature": ("FLOAT", {
                    "default": 0.20,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "0.20 es el valor estable probado. No subir de 0.40 para captioning."
                }),
            },
            "optional": {
                "extra_instructions": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Instrucciones adicionales por sesión sin tocar el system prompt base."
                }),
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": (
                        "Vacío → usa el default del formato seleccionado. "
                        "Relleno → lo usa como base (los modificadores nsfw/length/subject/extra se añaden igualmente). "
                        "Con format=Custom este campo es obligatorio."
                    )
                }),
                "output_dir": ("STRING", {
                    "default": "",
                    "tooltip": "Vacío → guarda los .txt en la misma carpeta que las imágenes. Relleno → usa este directorio."
                }),
                "save_captions": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "False → genera captions pero no escribe .txt a disco (modo preview)."
                }),
                "skip_existing": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "True → salta imágenes que ya tienen .txt, sin gastar tokens."
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "Vacío → usa variable de entorno ANTHROPIC_API_KEY (recomendado)."
                }),
            }
        }

    # ----------------------------------------------------------

    def generate_captions(
        self,
        image_folder,
        trigger_word,
        subject_description,
        format,
        nsfw,
        caption_length,
        model,
        temperature,
        extra_instructions="",
        system_prompt="",
        output_dir="",
        save_captions=True,
        skip_existing=True,
        api_key="",
    ):
        logs = []
        last_caption = ""

        # ---- Validaciones previas ----
        if not os.path.isdir(image_folder):
            return ("", f"[ERROR] La carpeta no existe: {image_folder}")

        if format == "Custom" and not system_prompt.strip():
            return ("", "[ERROR] format=Custom requiere system_prompt relleno.")

        key = api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return ("", "[ERROR] No se encontró ANTHROPIC_API_KEY (ni en el nodo ni como variable de entorno).")

        # ---- Recopilar imágenes ----
        images = sorted([
            f for f in os.listdir(image_folder)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
        ])

        if not images:
            return ("", f"[ERROR] No se encontraron imágenes en: {image_folder}")

        logs.append(f"[INFO] {len(images)} imágenes encontradas en {image_folder}")

        # ---- Directorio de guardado ----
        save_dir = output_dir.strip() if output_dir.strip() else image_folder

        # ---- System prompt ----
        sys_prompt = self._build_system_prompt(
            format, system_prompt, nsfw, caption_length,
            subject_description, extra_instructions
        )

        # ---- Cliente Anthropic ----
        client = anthropic.Anthropic(api_key=key)

        # ---- Procesar imágenes ----
        for fname in images:
            fname_base = os.path.splitext(fname)[0]
            img_path   = os.path.join(image_folder, fname)
            txt_path   = os.path.join(save_dir, fname_base + ".txt")

            # Skip existing
            if skip_existing and os.path.exists(txt_path):
                logs.append(f"[SKIP] {fname}")
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        last_caption = f.read().strip()
                except Exception:
                    pass
                continue

            # Cargar y codificar imagen
            try:
                img_b64, media_type = self._image_to_base64(img_path)
            except Exception as e:
                logs.append(f"[ERROR] {fname} — fallo al cargar imagen: {e}")
                continue

            # Mensaje de usuario
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
                        "media_type": media_type,
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": user_text},
            ]

            # Llamada API
            try:
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
                logs.append(f"[ERROR] {fname} — API: {e}")
                continue

            # Guardar
            if save_captions:
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(caption)
                    logs.append(f"[OK] {fname} — in:{tok_in} out:{tok_out}")
                except Exception as e:
                    logs.append(f"[WARN] {fname} — caption generado pero no guardado: {e}")
            else:
                logs.append(f"[OK] {fname} (no guardado, save_captions=False) — in:{tok_in} out:{tok_out}")

            last_caption = caption

        return (last_caption, "\n".join(logs))

    # ----------------------------------------------------------

    def _build_system_prompt(
        self, format, custom_prompt, nsfw, caption_length,
        subject_description, extra_instructions
    ):
        if custom_prompt.strip():
            base = custom_prompt.strip()
        elif format == "FLUX Dual":
            base = DEFAULT_PROMPT_FLUX
        else:
            base = DEFAULT_PROMPT_ZIT

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

    def _image_to_base64(self, img_path):
        ext = os.path.splitext(img_path)[1].lower()
        media_type_map = {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".webp": "image/webp",
            ".bmp":  "image/png",
        }
        media_type = media_type_map.get(ext, "image/jpeg")

        with Image.open(img_path) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            save_format = "PNG" if media_type == "image/png" else "JPEG"
            img.save(buf, format=save_format)
            return base64.standard_b64encode(buf.getvalue()).decode("utf-8"), media_type


# ============================================================
# REGISTRO
# ============================================================

NODE_CLASS_MAPPINGS = {
    "ClaudeCaptionGenerator": ClaudeCaptionGenerator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ClaudeCaptionGenerator": "Claude Caption Generator (Rafa)",
}
