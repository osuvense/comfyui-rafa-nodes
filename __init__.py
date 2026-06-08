"""
comfyui-rafa-nodes
Nodos custom de ComfyUI — github.com/osuvense/comfyui-rafa-nodes

Nodos incluidos:
- ResolutionPreset:           selector de resoluciones predefinidas para FLUX, ZIT y WAN
- ClaudePromptGenerator:      generación de prompts via Claude API para Z-Image Turbo
- ClaudeDatasetProfiler:      perfilado/auditoría de un dataset (nodo 1 del sistema de captioning post-shift)
- ClaudeCaptionGenerator:     captioning de imágenes via Claude API (multimodal) — nodo 2, paradigma de enmascarado
- ProfileReviewPause:         checkpoint humano entre Profiler y Captioner (modal de revisión/edición del perfil)
- PromptApprovalGate:         checkpoint humano entre Prompt Generator e inferencia (revisar/editar prompt + modo producción para bucle)
- (web/js) node-resize-panel: menú contextual para redimensionar nodos
- (web/js) prompt-generator-display: muestra prompt + pensamiento dentro del Prompt Generator (sin Show Text externos)
"""

from .resolution_preset import NODE_CLASS_MAPPINGS as RESOLUTION_MAPPINGS
from .resolution_preset import NODE_DISPLAY_NAME_MAPPINGS as RESOLUTION_DISPLAY

from .claude_prompt_generator import NODE_CLASS_MAPPINGS as CLAUDE_PROMPT_MAPPINGS
from .claude_prompt_generator import NODE_DISPLAY_NAME_MAPPINGS as CLAUDE_PROMPT_DISPLAY

from .claude_dataset_profiler import NODE_CLASS_MAPPINGS as CLAUDE_PROFILER_MAPPINGS
from .claude_dataset_profiler import NODE_DISPLAY_NAME_MAPPINGS as CLAUDE_PROFILER_DISPLAY

from .claude_caption_generator import NODE_CLASS_MAPPINGS as CLAUDE_CAPTION_MAPPINGS
from .claude_caption_generator import NODE_DISPLAY_NAME_MAPPINGS as CLAUDE_CAPTION_DISPLAY

from .profile_review_pause import NODE_CLASS_MAPPINGS as PROFILE_PAUSE_MAPPINGS
from .profile_review_pause import NODE_DISPLAY_NAME_MAPPINGS as PROFILE_PAUSE_DISPLAY

from .prompt_approval_gate import NODE_CLASS_MAPPINGS as PROMPT_GATE_MAPPINGS
from .prompt_approval_gate import NODE_DISPLAY_NAME_MAPPINGS as PROMPT_GATE_DISPLAY

NODE_CLASS_MAPPINGS = {
    **RESOLUTION_MAPPINGS,
    **CLAUDE_PROMPT_MAPPINGS,
    **CLAUDE_PROFILER_MAPPINGS,
    **CLAUDE_CAPTION_MAPPINGS,
    **PROFILE_PAUSE_MAPPINGS,
    **PROMPT_GATE_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **RESOLUTION_DISPLAY,
    **CLAUDE_PROMPT_DISPLAY,
    **CLAUDE_PROFILER_DISPLAY,
    **CLAUDE_CAPTION_DISPLAY,
    **PROFILE_PAUSE_DISPLAY,
    **PROMPT_GATE_DISPLAY,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
