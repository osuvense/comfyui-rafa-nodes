// prompt-approval-gate.js — frontend del nodo Prompt Approval Gate (Rafa)
// Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes
//
// UI INLINE (sin ventana emergente). Cuando el backend (prompt_approval_gate.py) pausa en
// modo "revisar y editar", empuja el prompt por WS ("rafa.prompt_gate"); aquí se vuelca al
// campo `approved_text` DENTRO del propio nodo, se resalta el nodo y se activa su botón
// "Aprobar y generar". Editas el campo en el nodo y pulsas el botón → POST
// /rafa/prompt_gate/resume con el texto editado → el workflow continúa con ese prompt.
//
// El texto aprobado queda en `approved_text`, que es lo que emite el modo "produccion
// (bucle)". El backend no cambia respecto a la versión con modal: misma pausa real
// (threading.Event) y misma ruta de resume.
//
// Robustez:
// - Botón permanente en el nodo; sólo actúa si hay una pausa viva para ese nodo.
// - execution_interrupted / execution_error → limpia el estado de espera del nodo.
// - Tras un refresh de página con pausa viva, setup() consulta GET /rafa/prompt_gate/pending
//   y vuelve a poner el nodo en estado "esperando" (el WS original se perdió).

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const EVENT_NAME = "rafa.prompt_gate";
const RESUME_URL = "/rafa/prompt_gate/resume";
const PENDING_URL = "/rafa/prompt_gate/pending";

const LABEL_IDLE = "Aprobar y generar  ▶";
const LABEL_WAIT = "⏸  APROBAR Y GENERAR  (pausado)";
const COL_WAIT = "#7c6af0";
const BG_WAIT = "#2a2350";

function findGateNode(nodeId) {
    return app.graph?.getNodeById?.(Number(nodeId)) ?? null;
}
function getWidget(node, name) {
    return node?.widgets?.find((w) => w.name === name) ?? null;
}

async function sendResume(nodeId, action, prompt) {
    const body = new FormData();
    body.append("node_id", nodeId);
    body.append("action", action);
    body.append("prompt", prompt);
    try {
        const resp = await api.fetchApi(RESUME_URL, { method: "POST", body });
        return (await resp.json()).ok === true;
    } catch (e) {
        console.error("[rafa.PromptApprovalGate] falló el POST de resume:", e);
        return false;
    }
}

// Pone/quita el estado visual de "esperando aprobación" en el nodo.
function setWaiting(node, waiting, prompt) {
    node._rafaWaiting = waiting;
    if (node._rafaApproveBtn) node._rafaApproveBtn.name = waiting ? LABEL_WAIT : LABEL_IDLE;

    if (waiting) {
        if (node._rafaColorSaved === undefined) {
            node._rafaColorSaved = node.color ?? null;
            node._rafaBgSaved = node.bgcolor ?? null;
        }
        node.color = COL_WAIT;
        node.bgcolor = BG_WAIT;
        if (prompt !== undefined && prompt !== null) {
            const w = getWidget(node, "approved_text");
            if (w) {
                w.value = prompt;
                if (w.inputEl) w.inputEl.value = prompt; // refresca el textarea DOM
            }
        }
    } else if (node._rafaColorSaved !== undefined) {
        node.color = node._rafaColorSaved;
        node.bgcolor = node._rafaBgSaved;
        node._rafaColorSaved = undefined;
        node._rafaBgSaved = undefined;
    }
    node.setDirtyCanvas?.(true, true);
}

async function approve(node) {
    if (!node._rafaWaiting || !node._rafaPendingId) return; // sin pausa viva, no hace nada
    const w = getWidget(node, "approved_text");
    const text = w ? (w.value ?? "") : "";
    const ok = await sendResume(node._rafaPendingId, "resume", text);
    if (!ok) {
        alert("Esta pausa ya no existe en el backend (¿cancelada o reanudada en otra pestaña?).");
    }
    node._rafaPendingId = null;
    setWaiting(node, false);
}

app.registerExtension({
    name: "rafa.PromptApprovalGate",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "PromptApprovalGate") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            const node = this;
            // Botón inline de aprobación. No se serializa en el workflow.
            node._rafaApproveBtn = node.addWidget("button", LABEL_IDLE, null, () => approve(node));
            node._rafaApproveBtn.serialize = false;
        };
    },

    async setup() {
        // Pausa empujada por el backend durante la ejecución.
        api.addEventListener(EVENT_NAME, (event) => {
            const nodeId = event.detail.node;
            const node = findGateNode(nodeId);
            if (!node) return;
            node._rafaPendingId = nodeId;
            setWaiting(node, true, event.detail.prompt);
        });

        // Workflow interrumpido o roto: limpiar el estado de espera de todos los gates.
        const clearAll = () => {
            for (const node of app.graph?._nodes ?? []) {
                if (node._rafaWaiting) {
                    node._rafaPendingId = null;
                    setWaiting(node, false);
                }
            }
        };
        api.addEventListener("execution_interrupted", clearAll);
        api.addEventListener("execution_error", clearAll);

        // Refresh de página con pausa viva: recuperar del backend (el WS original se perdió).
        try {
            const resp = await api.fetchApi(PENDING_URL);
            const data = await resp.json();
            for (const p of data.pending ?? []) {
                const node = findGateNode(p.node);
                if (node) {
                    node._rafaPendingId = p.node;
                    setWaiting(node, true, p.prompt);
                }
            }
        } catch (e) {
            console.warn("[rafa.PromptApprovalGate] no se pudo consultar pausas pendientes:", e);
        }
    },
});
