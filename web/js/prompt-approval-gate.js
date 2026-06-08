// prompt-approval-gate.js — frontend del nodo Prompt Approval Gate (Rafa)
// Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes
//
// Escucha el mensaje WS "rafa.prompt_gate" del backend (prompt_approval_gate.py), abre un
// modal con el prompt generado en un textarea editable y, al pulsar "Aprobar y generar",
// (1) escribe el texto en el widget `approved_text` del propio nodo (para que el modo
// producción lo emita en el bucle) y (2) devuelve el texto editado via POST
// /rafa/prompt_gate/resume (desbloquea el nodo → corre la inferencia con el prompt aprobado).
//
// Robustez (heredada de profile-review-pause.js):
// - Escape o "Minimizar" NO pierden la edición: el modal se oculta y queda un botón
//   flotante para reabrirlo (el DOM persiste).
// - Click fuera del panel NO cierra (evita perder ediciones por un misclick).
// - Si llega una segunda pausa con el modal abierto, se encola.
// - Tras un refresh de página con pausa viva, setup() consulta GET /rafa/prompt_gate/pending
//   y reabre el modal (el WS original se perdió).
// - Si el workflow se interrumpe/falla con el modal abierto, se cierra solo.

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const EVENT_NAME = "rafa.prompt_gate";
const RESUME_URL = "/rafa/prompt_gate/resume";
const PENDING_URL = "/rafa/prompt_gate/pending";

// Estado del modal: solo una revisión visible a la vez; el resto, en cola.
let current = null; // { node, prompt }
const queue = [];

app.registerExtension({
    name: "rafa.PromptApprovalGate",

    async setup() {
        const style = document.createElement("style");
        style.textContent = `
            #rafa-gate-overlay {
                position: fixed; inset: 0;
                background: rgba(0,0,0,0.55);
                z-index: 9999;
                display: flex; align-items: center; justify-content: center;
            }
            #rafa-gate-modal {
                background: #1a1a2e; border: 1px solid #444; border-radius: 8px;
                padding: 18px 22px;
                width: min(1000px, 88vw);
                height: min(640px, 86vh);
                display: flex; flex-direction: column;
                box-shadow: 0 8px 32px rgba(0,0,0,0.6);
                font-family: sans-serif; color: #eee;
            }
            #rafa-gate-modal h3 {
                margin: 0 0 4px 0; font-size: 14px; font-weight: 600;
                color: #aaa; text-transform: uppercase; letter-spacing: 0.05em;
            }
            #rafa-gate-sub {
                font-size: 11px; color: #666; margin-bottom: 10px;
            }
            #rafa-gate-text {
                flex: 1; resize: none; outline: none;
                background: #12121e; border: 1px solid #555; border-radius: 4px;
                color: #ddd; padding: 10px 12px;
                font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
                font-size: 13px; line-height: 1.5;
                white-space: pre-wrap; overflow: auto;
            }
            #rafa-gate-text:focus { border-color: #7c6af0; }
            #rafa-gate-footer {
                display: flex; align-items: center; gap: 10px; margin-top: 12px;
            }
            #rafa-gate-stats { font-size: 11px; color: #666; flex: 1; }
            #rafa-gate-footer button {
                padding: 8px 18px; border-radius: 4px; border: none;
                font-size: 13px; cursor: pointer;
            }
            #rafa-gate-cancel { background: #5a2330; color: #f0b5c0; }
            #rafa-gate-minimize { background: #333; color: #bbb; }
            #rafa-gate-resume { background: #7c6af0; color: #fff; font-weight: 600; }
            #rafa-gate-pill {
                position: fixed; right: 16px; bottom: 16px; z-index: 9998;
                background: #7c6af0; color: #fff;
                padding: 10px 16px; border-radius: 20px;
                font-family: sans-serif; font-size: 13px; font-weight: 600;
                cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.5);
            }
        `;
        document.head.appendChild(style);

        api.addEventListener(EVENT_NAME, (event) => {
            enqueueReview({ node: event.detail.node, prompt: event.detail.prompt });
        });

        api.addEventListener("execution_interrupted", () => dismissAll("Workflow interrumpido."));
        api.addEventListener("execution_error", () => dismissAll("Error en el workflow."));

        try {
            const resp = await api.fetchApi(PENDING_URL);
            const data = await resp.json();
            for (const p of data.pending ?? []) {
                enqueueReview({ node: p.node, prompt: p.prompt });
            }
        } catch (e) {
            console.warn("[rafa.PromptApprovalGate] no se pudo consultar pausas pendientes:", e);
        }
    },
});

function enqueueReview(item) {
    if (current && current.node === item.node) return; // duplicado (reconexión WS)
    if (queue.some((q) => q.node === item.node)) return;
    if (current) {
        queue.push(item);
        return;
    }
    showModal(item);
}

function nextInQueue() {
    current = null;
    const next = queue.shift();
    if (next) showModal(next);
}

function dismissAll(reason) {
    document.getElementById("rafa-gate-overlay")?.remove();
    document.getElementById("rafa-gate-pill")?.remove();
    queue.length = 0;
    if (current) {
        console.info(`[rafa.PromptApprovalGate] revisión descartada: ${reason}`);
        current = null;
    }
}

// Escribe el texto aprobado en el widget approved_text del nodo, para que el modo
// producción lo emita en el bucle. Silencioso si el nodo/widget no se encuentra.
function writeApprovedWidget(nodeId, text) {
    try {
        const node = app.graph.getNodeById(Number(nodeId));
        if (!node || !node.widgets) return;
        const w = node.widgets.find((w) => w.name === "approved_text");
        if (w) {
            w.value = text;
            node.setDirtyCanvas?.(true, true);
        }
    } catch (e) {
        console.warn("[rafa.PromptApprovalGate] no se pudo escribir approved_text:", e);
    }
}

function showModal(item) {
    current = item;
    document.getElementById("rafa-gate-overlay")?.remove();
    document.getElementById("rafa-gate-pill")?.remove();

    const overlay = document.createElement("div");
    overlay.id = "rafa-gate-overlay";
    overlay.innerHTML = `
        <div id="rafa-gate-modal">
            <h3>Revisar prompt antes de generar</h3>
            <div id="rafa-gate-sub">
                Nodo #${item.node} — el workflow está PAUSADO. Edita el prompt si quieres y pulsa
                "Aprobar y generar". El texto aprobado queda guardado para el modo producción (bucle).
            </div>
            <textarea id="rafa-gate-text" spellcheck="false"></textarea>
            <div id="rafa-gate-footer">
                <span id="rafa-gate-stats"></span>
                <button id="rafa-gate-cancel" title="Aborta el workflow entero (interrupt)">Cancelar</button>
                <button id="rafa-gate-minimize" title="Oculta el modal sin perder la edición (Esc)">Minimizar</button>
                <button id="rafa-gate-resume" title="Aprueba el texto y genera (Ctrl+Enter)">Aprobar y generar &rarr;</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const textarea = document.getElementById("rafa-gate-text");
    const stats = document.getElementById("rafa-gate-stats");
    textarea.value = item.prompt;

    function updateStats() {
        const words = textarea.value.trim() ? textarea.value.trim().split(/\s+/).length : 0;
        const edited = textarea.value !== item.prompt ? " — editado" : "";
        stats.textContent = `${words} palabras, ${textarea.value.length} chars${edited}`;
    }
    textarea.addEventListener("input", updateStats);
    updateStats();
    setTimeout(() => { textarea.focus(); }, 50);

    async function send(action) {
        const text = textarea.value;
        if (action === "resume") {
            writeApprovedWidget(item.node, text); // guardar para producción
        }
        const body = new FormData();
        body.append("node_id", item.node);
        body.append("action", action);
        body.append("prompt", text);
        let ok = false;
        try {
            const resp = await api.fetchApi(RESUME_URL, { method: "POST", body });
            ok = (await resp.json()).ok === true;
        } catch (e) {
            console.error("[rafa.PromptApprovalGate] falló el POST de resume:", e);
        }
        if (!ok) {
            alert("Esta pausa ya no existe en el backend (¿workflow cancelado o reanudado desde otra pestaña?).");
        }
        overlay.remove();
        nextInQueue();
    }

    document.getElementById("rafa-gate-resume").addEventListener("click", () => send("resume"));
    document.getElementById("rafa-gate-cancel").addEventListener("click", () => {
        if (confirm("¿Cancelar el workflow entero? La inferencia no llegará a ejecutarse.")) {
            send("cancel");
        }
    });

    function minimize() {
        overlay.style.display = "none";
        const pill = document.createElement("div");
        pill.id = "rafa-gate-pill";
        pill.textContent = "Prompt pendiente de revisar — reabrir";
        pill.addEventListener("click", () => {
            pill.remove();
            overlay.style.display = "flex";
            setTimeout(() => { textarea.focus(); }, 50);
        });
        document.body.appendChild(pill);
    }
    document.getElementById("rafa-gate-minimize").addEventListener("click", minimize);

    overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            e.preventDefault();
            minimize();
        }
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            send("resume");
        }
    });
    // Click fuera NO cierra: una edición larga no se pierde por un misclick.
}
