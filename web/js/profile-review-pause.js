// profile-review-pause.js — frontend del nodo Profile Review Pause (Rafa)
// Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes
//
// Escucha el mensaje WS "rafa.profile_review" del backend (profile_review_pause.py),
// abre un modal con el Dataset Profile en un textarea editable y, al pulsar Reanudar,
// devuelve el texto editado via POST /rafa/profile_review/resume (desbloquea el nodo).
//
// Robustez:
// - Escape o "Minimizar" NO pierden la edicion: el modal se oculta y queda un boton
//   flotante "Revision pendiente" para reabrirlo (el DOM persiste).
// - Click fuera del panel NO cierra (evita perder ediciones largas por un misclick).
// - Si llega una segunda pausa con el modal abierto (dos nodos pause en un workflow),
//   se encola y se muestra al resolver la primera.
// - Tras un refresh de pagina con pausa viva, setup() consulta GET
//   /rafa/profile_review/pending y reabre el modal (el WS original se perdio).
// - Si el workflow se interrumpe/falla con el modal abierto, se cierra solo
//   (listeners de execution_interrupted / execution_error).

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const EVENT_NAME = "rafa.profile_review";
const RESUME_URL = "/rafa/profile_review/resume";
const PENDING_URL = "/rafa/profile_review/pending";

// Estado del modal: solo una revision visible a la vez; el resto, en cola.
let current = null; // { node, profile }
const queue = [];

app.registerExtension({
    name: "rafa.ProfileReviewPause",

    async setup() {
        const style = document.createElement("style");
        style.textContent = `
            #rafa-review-overlay {
                position: fixed; inset: 0;
                background: rgba(0,0,0,0.55);
                z-index: 9999;
                display: flex; align-items: center; justify-content: center;
            }
            #rafa-review-modal {
                background: #1a1a2e; border: 1px solid #444; border-radius: 8px;
                padding: 18px 22px;
                width: min(1100px, 88vw);
                height: min(820px, 88vh);
                display: flex; flex-direction: column;
                box-shadow: 0 8px 32px rgba(0,0,0,0.6);
                font-family: sans-serif; color: #eee;
            }
            #rafa-review-modal h3 {
                margin: 0 0 4px 0; font-size: 14px; font-weight: 600;
                color: #aaa; text-transform: uppercase; letter-spacing: 0.05em;
            }
            #rafa-review-sub {
                font-size: 11px; color: #666; margin-bottom: 10px;
            }
            #rafa-review-text {
                flex: 1; resize: none; outline: none;
                background: #12121e; border: 1px solid #555; border-radius: 4px;
                color: #ddd; padding: 10px 12px;
                font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
                font-size: 12.5px; line-height: 1.45;
                white-space: pre; overflow: auto;
            }
            #rafa-review-text:focus { border-color: #7c6af0; }
            #rafa-review-footer {
                display: flex; align-items: center; gap: 10px; margin-top: 12px;
            }
            #rafa-review-stats { font-size: 11px; color: #666; flex: 1; }
            #rafa-review-footer button {
                padding: 8px 18px; border-radius: 4px; border: none;
                font-size: 13px; cursor: pointer;
            }
            #rafa-review-cancel { background: #5a2330; color: #f0b5c0; }
            #rafa-review-minimize { background: #333; color: #bbb; }
            #rafa-review-resume { background: #7c6af0; color: #fff; font-weight: 600; }
            #rafa-review-pill {
                position: fixed; right: 16px; bottom: 16px; z-index: 9998;
                background: #7c6af0; color: #fff;
                padding: 10px 16px; border-radius: 20px;
                font-family: sans-serif; font-size: 13px; font-weight: 600;
                cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.5);
            }
        `;
        document.head.appendChild(style);

        // Pausa nueva empujada por el backend durante la ejecucion.
        api.addEventListener(EVENT_NAME, (event) => {
            enqueueReview({ node: event.detail.node, profile: event.detail.profile });
        });

        // Workflow interrumpido o roto: la pausa ya no existe en el backend.
        api.addEventListener("execution_interrupted", () => dismissAll("Workflow interrumpido."));
        api.addEventListener("execution_error", () => dismissAll("Error en el workflow."));

        // Refresh de pagina con pausa viva: el WS se perdio; recuperar del backend.
        try {
            const resp = await api.fetchApi(PENDING_URL);
            const data = await resp.json();
            for (const p of data.pending ?? []) {
                enqueueReview({ node: p.node, profile: p.profile });
            }
        } catch (e) {
            console.warn("[rafa.ProfileReviewPause] no se pudo consultar pausas pendientes:", e);
        }
    },
});

function enqueueReview(item) {
    if (current && current.node === item.node) return; // duplicado (reconexion WS)
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
    document.getElementById("rafa-review-overlay")?.remove();
    document.getElementById("rafa-review-pill")?.remove();
    queue.length = 0;
    if (current) {
        console.info(`[rafa.ProfileReviewPause] revision descartada: ${reason}`);
        current = null;
    }
}

function showModal(item) {
    current = item;
    document.getElementById("rafa-review-overlay")?.remove();
    document.getElementById("rafa-review-pill")?.remove();

    const overlay = document.createElement("div");
    overlay.id = "rafa-review-overlay";
    overlay.innerHTML = `
        <div id="rafa-review-modal">
            <h3>Revision del Dataset Profile</h3>
            <div id="rafa-review-sub">
                Nodo #${item.node} — el workflow esta PAUSADO esperando esta revision.
                Edita lo que haga falta (invariantes borderline, vocabulario, curacion) y pulsa Reanudar.
            </div>
            <textarea id="rafa-review-text" spellcheck="false"></textarea>
            <div id="rafa-review-footer">
                <span id="rafa-review-stats"></span>
                <button id="rafa-review-cancel" title="Aborta el workflow entero (interrupt)">Cancelar workflow</button>
                <button id="rafa-review-minimize" title="Oculta el modal sin perder la edicion (Esc)">Minimizar</button>
                <button id="rafa-review-resume" title="Envia el texto tal cual este y reanuda (Ctrl+Enter)">Reanudar &rarr;</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const textarea = document.getElementById("rafa-review-text");
    const stats = document.getElementById("rafa-review-stats");
    textarea.value = item.profile;

    function updateStats() {
        const lines = textarea.value.split("\n").length;
        const edited = textarea.value !== item.profile ? " — editado" : "";
        stats.textContent = `${lines} lineas, ${textarea.value.length} chars${edited}`;
    }
    textarea.addEventListener("input", updateStats);
    updateStats();
    setTimeout(() => textarea.focus(), 50);

    async function send(action) {
        const body = new FormData();
        body.append("node_id", item.node);
        body.append("action", action);
        body.append("profile", textarea.value);
        let ok = false;
        try {
            const resp = await api.fetchApi(RESUME_URL, { method: "POST", body });
            ok = (await resp.json()).ok === true;
        } catch (e) {
            console.error("[rafa.ProfileReviewPause] fallo el POST de resume:", e);
        }
        if (!ok) {
            alert("Esta pausa ya no existe en el backend (¿workflow cancelado o reanudado desde otra pestana?).");
        }
        overlay.remove();
        nextInQueue();
    }

    document.getElementById("rafa-review-resume").addEventListener("click", () => send("resume"));
    document.getElementById("rafa-review-cancel").addEventListener("click", () => {
        if (confirm("¿Cancelar el workflow entero? El Captioner no llegara a ejecutarse.")) {
            send("cancel");
        }
    });

    function minimize() {
        overlay.style.display = "none";
        const pill = document.createElement("div");
        pill.id = "rafa-review-pill";
        pill.textContent = "Revision pendiente — reabrir";
        pill.addEventListener("click", () => {
            pill.remove();
            overlay.style.display = "flex";
            setTimeout(() => textarea.focus(), 50);
        });
        document.body.appendChild(pill);
    }
    document.getElementById("rafa-review-minimize").addEventListener("click", minimize);

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
    // Click fuera NO cierra: una edicion larga no se pierde por un misclick.
}
