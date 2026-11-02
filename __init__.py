"""
comfyui-rafa-nodes
Nodos custom de ComfyUI — github.com/osuvense/comfyui-rafa-nodes

Nodos incluidos:
- ResolutionPreset:           selector de resoluciones predefinidas para FLUX, ZIT y WAN (lista fija; lo usan workflows y bot)
- RafaResolution:             resoluciones v2: las lee de los perfiles .md de modelos (fuera del repo)
- RafaPromptStudio:           prompts v2 (Prompt Studio): perfiles .md de modelos, léxicos y personajes fuera del repo
- RafaPromptStudioFreeFuse:   Prompt Studio para FreeFuse (hasta 4 personajes, prompt por bloques, spans literales)
- RafaFreeFuseSpans:          spans, fondo y adapters para FreeFuseConceptMap, recalculados desde el prompt aprobado
- RafaRepartoFreeFuse:        reparto de personajes (1-4) + carga de sus LoRAs con FreeFuseLoRALoader
- RafaIdeas / RafaElegirIdea: tandas de ideas de escena (Claude) con historial para no repetir y encadenar; selector para la escena
- ClaudePromptGenerator:      generador de prompts v1 (legacy; lo importa el bot v2)
- ClaudeDatasetProfiler:      perfilado/auditoría de un dataset (nodo 1 del sistema de captioning post-shift)
- ClaudeCaptionGenerator:     captioning de imágenes via Claude API (multimodal) — nodo 2, paradigma de enmascarado
- ProfileReviewPause:         checkpoint humano entre Profiler y Captioner (modal de revisión/edición del perfil)
- PromptApprovalGate:         checkpoint humano entre Prompt Generator e inferencia (revisar/editar prompt + modo producción para bucle)
- (web/js) node-resize-panel: menú contextual para redimensionar nodos
"""

from .resolution_preset import NODE_CLASS_MAPPINGS as RESOLUTION_MAPPINGS
from .resolution_preset import NODE_DISPLAY_NAME_MAPPINGS as RESOLUTION_DISPLAY

from .rafa_resolution import NODE_CLASS_MAPPINGS as RES2_MAPPINGS
from .rafa_resolution import NODE_DISPLAY_NAME_MAPPINGS as RES2_DISPLAY

from .rafa_prompt_studio import NODE_CLASS_MAPPINGS as STUDIO_MAPPINGS
from .rafa_prompt_studio import NODE_DISPLAY_NAME_MAPPINGS as STUDIO_DISPLAY

from .rafa_prompt_studio_freefuse import NODE_CLASS_MAPPINGS as STUDIO_FF_MAPPINGS
from .rafa_prompt_studio_freefuse import NODE_DISPLAY_NAME_MAPPINGS as STUDIO_FF_DISPLAY

from .rafa_ideas import NODE_CLASS_MAPPINGS as IDEAS_MAPPINGS
from .rafa_ideas import NODE_DISPLAY_NAME_MAPPINGS as IDEAS_DISPLAY

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
    **RES2_MAPPINGS,
    **STUDIO_MAPPINGS,
    **STUDIO_FF_MAPPINGS,
    **IDEAS_MAPPINGS,
    **CLAUDE_PROMPT_MAPPINGS,
    **CLAUDE_PROFILER_MAPPINGS,
    **CLAUDE_CAPTION_MAPPINGS,
    **PROFILE_PAUSE_MAPPINGS,
    **PROMPT_GATE_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **RESOLUTION_DISPLAY,
    **RES2_DISPLAY,
    **STUDIO_DISPLAY,
    **STUDIO_FF_DISPLAY,
    **IDEAS_DISPLAY,
    **CLAUDE_PROMPT_DISPLAY,
    **CLAUDE_PROFILER_DISPLAY,
    **CLAUDE_CAPTION_DISPLAY,
    **PROFILE_PAUSE_DISPLAY,
    **PROMPT_GATE_DISPLAY,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
