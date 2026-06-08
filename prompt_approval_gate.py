# -*- coding: utf-8 -*-
"""
prompt_approval_gate.py
Nodo ComfyUI — Prompt Approval Gate (checkpoint humano entre el Prompt Generator y la inferencia).
Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes

Se coloca entre ClaudePromptGenerator y el resto del workflow de inferencia. Resuelve el
flujo que pidió Rafa: generar un prompt, revisarlo/editarlo, y solo cuando guste dejar
correr la inferencia — y luego generar imágenes en bucle con ese mismo prompt sin volver
a llamar a la API ni pararse a confirmar en cada imagen.

DOS MODOS (widget `mode`):

- "revisar y editar"  → pausa el workflow al llegar aquí, empuja el prompt entrante al
  frontend (PromptServer.send_sync) y BLOQUEA hasta que el operador lo revisa/edita en un
  modal (web/js/prompt-approval-gate.js) y pulsa "Aprobar y generar". Devuelve el texto
  editado hacia la inferencia (corre UNA imagen con el prompt aprobado). El texto aprobado
  se guarda además en el widget `approved_text` del propio nodo (lo escribe el JS) para
  que el modo producción lo tenga disponible.

- "produccion (bucle)" → NO pausa. Emite directamente `approved_text` (el prompt ya
  aprobado) y deja correr la inferencia. Con Auto Queue nativo de ComfyUI + el seed del
  KSampler en randomize, genera imágenes en bucle sin parar y sin tocar el generador.

POR QUÉ UN NODO APARTE Y NO DENTRO DEL GENERADOR:
El ClaudePromptGenerator cachea por hash de sus inputs (IS_CHANGED, fix c585c34): si nada
cambia NO re-llama a la API. Meter aquí un toggle de aprobación DENTRO del generador
alteraría ese hash y volvería a gastar tokens en cada Queue (el bug que ya sufrimos). Por
eso la aprobación vive en este gate, aguas abajo, sin tocar los inputs del generador.
Requisito operativo del bucle: el `seed` del generador en FIXED (si está en randomize,
vuelve el re-pedido a la API).

Mecánica de la pausa (idéntica a ProfileReviewPause, [REF]-nodo-captioning.md § 5.6):
- El executor de ComfyUI corre en un thread distinto del servidor aiohttp, por lo que
  bloquear aquí con threading.Event NO impide que el servidor reciba el POST de Resume.
- El botón Cancelar del modal (o el Cancel nativo) aborta vía InterruptProcessingException;
  el bloqueo comprueba el flag de interrupt cada 0.3 s.
- GET /rafa/prompt_gate/pending permite al frontend re-abrir el modal tras un refresh de
  página con una pausa todavía viva (el send_sync original se habría perdido).
"""

import threading
import time

from aiohttp import web
from server import PromptServer
import comfy.model_management as mm

try:
    # Ruta vigente del ExecutionBlocker (ComfyUI con el modelo de ejecución invertido).
    from comfy_execution.graph import ExecutionBlocker
except Exception:  # pragma: no cover - fallback defensivo por si cambia el módulo
    ExecutionBlocker = None

# Mensaje WS backend -> frontend
PAUSE_EVENT = "rafa.prompt_gate"

# Polling del Event: corto para que el Cancel nativo de ComfyUI responda rápido.
WAIT_TICK_SECONDS = 0.3

# Etiquetas de modo (deben coincidir EXACTAS con las del dropdown y el JS)
MODE_REVIEW = "revisar y editar"
MODE_PROD = "produccion (bucle)"
MODES = [MODE_REVIEW, MODE_PROD]


def _block(msg):
    """Devuelve una tupla de 4 ExecutionBlocker para cortar limpio la inferencia.
    Si el módulo no estuviera disponible, cae a strings vacíos (degradación suave)."""
    if ExecutionBlocker is not None:
        b = ExecutionBlocker(msg)
        return (b, b, b, b)
    return ("", "", "", "")


class PromptApprovalGate:
    """
    Checkpoint humano entre el Prompt Generator y la inferencia. Revisa/edita el prompt
    (modo revisar) o lo emite ya aprobado para generar en bucle (modo producción).
    """

    CATEGORY = "rafa"
    FUNCTION = "gate"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative", "clip_l", "t5xxl")

    # Pausas vivas: node_id -> {"event": Event, "prompt": str, "result": dict|None, "ts": float}
    _pending = {}
    _lock = threading.Lock()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "forceInput": True,
                    "tooltip": (
                        "Prompt del Claude Prompt Generator (conexión nodo a nodo). En modo "
                        "revisar se muestra en el modal para editarlo; en producción se ignora "
                        "y se emite `approved_text`."
                    )
                }),
                "mode": (MODES, {
                    "default": MODE_REVIEW,
                    "tooltip": (
                        "revisar y editar → pausa, abre el modal, editas y apruebas (corre 1 "
                        "imagen con el prompt aprobado). produccion (bucle) → no pausa, emite el "
                        "prompt ya aprobado; con Auto Queue + seed del KSampler en randomize "
                        "generas en bucle sin re-pedir a la API ni pararte."
                    )
                }),
            },
            "optional": {
                "negative": ("STRING", {"forceInput": True, "tooltip": "Negative del generador; pasa tal cual."}),
                "clip_l": ("STRING", {"forceInput": True, "tooltip": "Solo FLUX.1 legacy; pasa tal cual."}),
                "t5xxl": ("STRING", {"forceInput": True, "tooltip": "Solo FLUX.1 legacy; pasa tal cual."}),
                "approved_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": (
                        "Prompt aprobado. Lo rellena el modal al pulsar Aprobar; también puedes "
                        "editarlo a mano. Es lo que emite el modo producción en el bucle."
                    )
                }),
            },
            "hidden": {
                "node_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, mode=MODE_REVIEW, approved_text="", **kwargs):
        # Revisar: debe ejecutarse SIEMPRE para pausar en cada Queue (como el checkpoint del
        # captioning). Producción: cachea por el texto aprobado, así el gate no estorba al
        # bucle (el KSampler downstream re-ejecuta por su propio seed) y NO se vuelve a tocar
        # el generador más allá de su cache.
        if mode == MODE_PROD:
            import hashlib
            return hashlib.sha256(("prod::" + (approved_text or "")).encode("utf-8")).hexdigest()
        return float("nan")

    # ----------------------------------------------------------

    def gate(self, prompt, mode, negative="", clip_l="", t5xxl="", approved_text="", node_id=None):
        negative = negative or ""
        clip_l = clip_l or ""
        t5xxl = t5xxl or ""

        # ---- Modo producción: sin pausa, emite el prompt aprobado ----
        if mode == MODE_PROD:
            text = (approved_text or "").strip()
            if not text:
                # No hay nada aprobado: corta la inferencia con un mensaje útil en vez de
                # generar con un prompt vacío.
                return _block(
                    "PromptApprovalGate: no hay prompt aprobado. Cambia a modo "
                    "'revisar y editar', aprueba un prompt y vuelve a producción."
                )
            return (text, negative, clip_l, t5xxl)

        # ---- Modo revisar: pausa, modal de edición, emite el texto editado ----
        incoming = prompt if prompt is not None else (approved_text or "")
        cls = PromptApprovalGate
        event = threading.Event()
        with cls._lock:
            cls._pending[node_id] = {
                "event": event,
                "prompt": incoming,
                "result": None,
                "ts": time.time(),
            }

        try:
            PromptServer.instance.send_sync(PAUSE_EVENT, {
                "node": node_id,
                "prompt": incoming,
            })

            # Bloqueo con tick corto: respeta el Cancel nativo de ComfyUI (interrupt).
            while not event.wait(WAIT_TICK_SECONDS):
                mm.throw_exception_if_processing_interrupted()

            with cls._lock:
                entry = cls._pending.get(node_id)
                result = entry.get("result") if entry else None

            if result is None:
                raise mm.InterruptProcessingException()
            if result.get("action") == "cancel":
                raise mm.InterruptProcessingException()

            edited = result.get("prompt", incoming)
            return (edited, negative, clip_l, t5xxl)
        finally:
            with cls._lock:
                cls._pending.pop(node_id, None)

    # ----------------------------------------------------------
    # Llamados desde las rutas HTTP (thread del servidor)

    @classmethod
    def resolve(cls, node_id, action, prompt):
        """Resuelve una pausa viva. Devuelve True si existía, False si no."""
        with cls._lock:
            entry = cls._pending.get(node_id)
            if entry is None or entry["result"] is not None:
                return False
            entry["result"] = {"action": action, "prompt": prompt}
            entry["event"].set()
            return True

    @classmethod
    def pending_list(cls):
        """Pausas aún sin resolver (para re-abrir el modal tras un refresh)."""
        with cls._lock:
            return [
                {"node": node_id, "prompt": entry["prompt"]}
                for node_id, entry in cls._pending.items()
                if entry["result"] is None
            ]


# ============================================================
# RUTAS HTTP (frontend -> backend)
# ============================================================

routes = PromptServer.instance.routes


@routes.post("/rafa/prompt_gate/resume")
async def _rafa_prompt_gate_resume(request):
    data = await request.post()
    node_id = data.get("node_id", "")
    action = data.get("action", "resume")
    prompt = data.get("prompt", "")
    ok = PromptApprovalGate.resolve(node_id, action, prompt)
    return web.json_response({"ok": ok})


@routes.get("/rafa/prompt_gate/pending")
async def _rafa_prompt_gate_pending(request):
    return web.json_response({"pending": PromptApprovalGate.pending_list()})


# ============================================================
# REGISTRO
# ============================================================

NODE_CLASS_MAPPINGS = {
    "PromptApprovalGate": PromptApprovalGate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptApprovalGate": "Prompt Approval Gate (Rafa)",
}
