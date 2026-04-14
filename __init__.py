"""
comfyui-rafa-nodes
Nodos custom de ComfyUI — github.com/osuvense/comfyui-rafa-nodes

Nodos incluidos:
- ResolutionPreset:          selector de resoluciones predefinidas para FLUX, ZIT y WAN
- ClaudePromptGenerator:     generación de prompts via Claude API para Z-Image Turbo
- ClaudeCaptionGenerator:    captioning de imágenes via Claude API (multimodal) para datasets LoRA
- (web/js) node-resize-panel: menú contextual para redimensionar nodos
"""

from .resolution_preset import NODE_CLASS_MAPPINGS as RESOLUTION_MAPPINGS
from .resolution_preset import NODE_DISPLAY_NAME_MAPPINGS as RESOLUTION_DISPLAY

from .claude_prompt_generator import NODE_CLASS_MAPPINGS as CLAUDE_PROMPT_MAPPINGS
from .claude_prompt_generator import NODE_DISPLAY_NAME_MAPPINGS as CLAUDE_PROMPT_DISPLAY

from .claude_caption_generator import NODE_CLASS_MAPPINGS as CLAUDE_CAPTION_MAPPINGS
from .claude_caption_generator import NODE_DISPLAY_NAME_MAPPINGS as CLAUDE_CAPTION_DISPLAY

NODE_CLASS_MAPPINGS = {
    **RESOLUTION_MAPPINGS,
    **CLAUDE_PROMPT_MAPPINGS,
    **CLAUDE_CAPTION_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **RESOLUTION_DISPLAY,
    **CLAUDE_PROMPT_DISPLAY,
    **CLAUDE_CAPTION_DISPLAY,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
