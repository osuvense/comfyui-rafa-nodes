"""
profile_review_pause.py
Nodo ComfyUI — Profile Review Pause (checkpoint humano del sistema de captioning post-shift).
Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes

Se coloca entre el Dataset Profiler y el Captioner (Opción B, [REF]-nodo-captioning.md § 5.6):
recibe el Dataset Profile, lo empuja al frontend (PromptServer.send_sync), BLOQUEA la
ejecución del workflow hasta que el operador lo revisa/edita en un modal (web/js/
profile-review-pause.js) y pulsa Reanudar, y devuelve el texto editado hacia el Captioner.

"La máquina propone; el operador decide" — este nodo es donde el operador decide.

Mecánica:
- El executor de ComfyUI corre en un thread distinto del servidor aiohttp, por lo que
  bloquear aquí con threading.Event NO impide que el servidor reciba el POST de Resume.
- El botón Cancelar del modal (o el Cancel nativo de ComfyUI) aborta vía
  InterruptProcessingException; el bloqueo comprueba el flag de interrupt cada 0.3 s.
- GET /rafa/profile_review/pending permite al frontend re-abrir el modal tras un
  refresh de página con una pausa todavía viva (el send_sync original se habría perdido).

Diseño: [REF]-nodo-captioning.md § 5.6 (decisión 29 may 2026, revisión 2).
"""

import threading
import time

from aiohttp import web
from server import PromptServer
import comfy.model_management as mm

# Mensaje WS backend -> frontend
PAUSE_EVENT = "rafa.profile_review"

# Polling del Event: corto para que el Cancel nativo de ComfyUI responda rápido.
WAIT_TICK_SECONDS = 0.3


class ProfileReviewPause:
    """
    Checkpoint humano entre Profiler y Captioner. Pausa el workflow, muestra el perfil
    en un modal editable en el navegador y devuelve la versión editada al reanudar.
    """

    CATEGORY = "rafa"
    OUTPUT_NODE = True
    FUNCTION = "review"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("dataset_profile", "log")

    # Pausas vivas: node_id -> {"event": Event, "profile": str, "result": dict|None, "ts": float}
    # El node_id de ComfyUI es único por nodo del grafo; si el mismo workflow corre dos
    # veces, la segunda ejecución reutiliza la clave (la primera ya se resolvió).
    _pending = {}
    _lock = threading.Lock()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "dataset_profile": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Perfil del Dataset Profiler (conexión nodo a nodo). Se muestra en el "
                        "modal de revisión y se emite editado por el output homónimo."
                    )
                }),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "label_on": "pausar y revisar",
                    "label_off": "passthrough (sin pausa)",
                    "tooltip": (
                        "ON → pausa el workflow y abre el modal de revisión (flujo normal). "
                        "OFF → deja pasar el perfil tal cual, sin pausa (vía exprés / re-runs "
                        "en los que el perfil ya está validado)."
                    )
                }),
            },
            "hidden": {
                "node_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Checkpoint humano: debe ejecutarse en cada Queue aunque los inputs no cambien
        # (mismo criterio que Profiler/Captioner, fix 9924c89 — ComfyUI cachearía el nodo
        # y saltaría la pausa directo al Captioner).
        return float("nan")

    # ----------------------------------------------------------

    def review(self, dataset_profile, enabled, node_id):
        if not enabled:
            return (dataset_profile, "[PAUSE] passthrough (enabled=OFF): perfil sin revisar.")

        cls = ProfileReviewPause
        event = threading.Event()
        with cls._lock:
            cls._pending[node_id] = {
                "event": event,
                "profile": dataset_profile,
                "result": None,
                "ts": time.time(),
            }

        try:
            PromptServer.instance.send_sync(PAUSE_EVENT, {
                "node": node_id,
                "profile": dataset_profile,
            })

            # Bloqueo con tick corto: respeta el Cancel nativo de ComfyUI (interrupt).
            while not event.wait(WAIT_TICK_SECONDS):
                mm.throw_exception_if_processing_interrupted()

            with cls._lock:
                entry = cls._pending.get(node_id)
                result = entry.get("result") if entry else None

            if result is None:
                # Event disparado sin resultado: no debería pasar; tratar como interrupt.
                raise mm.InterruptProcessingException()

            if result.get("action") == "cancel":
                raise mm.InterruptProcessingException()

            edited = result.get("profile", dataset_profile)
            waited = time.time() - entry["ts"]
            changed = "editado" if edited != dataset_profile else "sin cambios"
            log = (
                f"[PAUSE] perfil revisado y reanudado ({changed}; "
                f"{len(edited)} chars; espera {waited:.0f}s)."
            )
            return (edited, log)
        finally:
            with cls._lock:
                cls._pending.pop(node_id, None)

    # ----------------------------------------------------------
    # Llamados desde las rutas HTTP (thread del servidor)

    @classmethod
    def resolve(cls, node_id, action, profile):
        """Resuelve una pausa viva. Devuelve True si existía, False si no."""
        with cls._lock:
            entry = cls._pending.get(node_id)
            if entry is None or entry["result"] is not None:
                return False
            entry["result"] = {"action": action, "profile": profile}
            entry["event"].set()
            return True

    @classmethod
    def pending_list(cls):
        """Pausas aún sin resolver (para re-abrir el modal tras un refresh)."""
        with cls._lock:
            return [
                {"node": node_id, "profile": entry["profile"]}
                for node_id, entry in cls._pending.items()
                if entry["result"] is None
            ]


# ============================================================
# RUTAS HTTP (frontend -> backend)
# ============================================================
# No definir los handlers dentro de la clase: el decorador @routes hace demasiado
# trabajo (tip de docs.comfy.org/development/comfyui-server/comms_routes). Handlers
# fuera, delegando en classmethods.

routes = PromptServer.instance.routes


@routes.post("/rafa/profile_review/resume")
async def _rafa_profile_review_resume(request):
    data = await request.post()
    node_id = data.get("node_id", "")
    action = data.get("action", "resume")
    profile = data.get("profile", "")
    ok = ProfileReviewPause.resolve(node_id, action, profile)
    return web.json_response({"ok": ok})


@routes.get("/rafa/profile_review/pending")
async def _rafa_profile_review_pending(request):
    return web.json_response({"pending": ProfileReviewPause.pending_list()})


# ============================================================
# REGISTRO
# ============================================================

NODE_CLASS_MAPPINGS = {
    "ProfileReviewPause": ProfileReviewPause,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ProfileReviewPause": "Profile Review Pause (Rafa)",
}
