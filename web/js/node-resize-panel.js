import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "rafa.NodeSizePanel",

    async setup() {
        const style = document.createElement("style");
        style.textContent = `
            #rafa-size-modal-overlay {
                position: fixed; inset: 0;
                background: rgba(0,0,0,0.5);
                z-index: 9999;
                display: flex; align-items: center; justify-content: center;
            }
            #rafa-size-modal {
                background: #1a1a2e; border: 1px solid #444; border-radius: 8px;
                padding: 20px 24px; min-width: 260px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.6);
                font-family: sans-serif; color: #eee;
            }
            #rafa-size-modal h3 {
                margin: 0 0 16px 0; font-size: 14px; font-weight: 600;
                color: #aaa; text-transform: uppercase; letter-spacing: 0.05em;
            }
            .rafa-size-row { display: flex; align-items: center; margin-bottom: 12px; gap: 10px; }
            .rafa-size-row label { width: 60px; font-size: 13px; color: #ccc; }
            .rafa-size-row input {
                flex: 1; background: #2a2a3e; border: 1px solid #555;
                border-radius: 4px; color: #fff; padding: 6px 10px;
                font-size: 14px; outline: none;
            }
            .rafa-size-row input:focus { border-color: #7c6af0; }
            .rafa-size-row input.rafa-invalid { border-color: #e05; }
            .rafa-size-hint { font-size: 11px; color: #666; margin-bottom: 10px; }
            .rafa-size-buttons { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
            .rafa-size-buttons button { padding: 7px 18px; border-radius: 4px; border: none; font-size: 13px; cursor: pointer; }
            #rafa-size-cancel { background: #333; color: #bbb; }
            #rafa-size-apply { background: #7c6af0; color: #fff; }
            #rafa-size-warning {
                font-size: 12px; color: #f90; padding: 6px 8px;
                background: #2a1a00; border-radius: 4px;
                border-left: 3px solid #f90; margin-bottom: 8px;
            }
        `;
        document.head.appendChild(style);
    },

    // New ComfyUI context menu API
    getNodeMenuItems(node) {
        return [
            {
                content: "Tamano del nodo...",
                callback: () => showSizeModal(node)
            }
        ];
    }
});

function showSizeModal(node) {
    document.getElementById("rafa-size-modal-overlay")?.remove();

    const currentW = Math.round(node.size[0]);
    const currentH = Math.round(node.size[1]);
    const minSize = node.computeSize ? node.computeSize() : [50, 30];
    const minW = Math.round(minSize[0]);
    const minH = Math.round(minSize[1]);

    const overlay = document.createElement("div");
    overlay.id = "rafa-size-modal-overlay";
    overlay.innerHTML = `
        <div id="rafa-size-modal">
            <h3>Tamano del nodo</h3>
            <div class="rafa-size-row">
                <label>Ancho</label>
                <input id="rafa-w" type="number" min="${minW}" max="2000" value="${currentW}" />
            </div>
            <div class="rafa-size-row">
                <label>Alto</label>
                <input id="rafa-h" type="number" min="${minH}" max="2000" value="${currentH}" />
            </div>
            <div class="rafa-size-hint">
                Actual: ${currentW} x ${currentH} px | Minimo: ${minW} x ${minH} px
            </div>
            <div id="rafa-size-warning" style="display:none;"></div>
            <div class="rafa-size-buttons">
                <button id="rafa-size-cancel">Cancelar</button>
                <button id="rafa-size-apply">Aplicar</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    const wInput = document.getElementById("rafa-w");
    const hInput = document.getElementById("rafa-h");
    const warning = document.getElementById("rafa-size-warning");

    setTimeout(() => wInput.select(), 50);

    function checkWarnings() {
        const wVal = parseInt(wInput.value);
        const hVal = parseInt(hInput.value);
        const msgs = [];
        if (!isNaN(hVal) && hVal < minH) {
            msgs.push("Aviso: Alto minimo " + minH + " px. El valor " + hVal + " sera ignorado por LiteGraph.");
            hInput.classList.add("rafa-invalid");
        } else { hInput.classList.remove("rafa-invalid"); }
        if (!isNaN(wVal) && wVal < minW) {
            msgs.push("Aviso: Ancho minimo " + minW + " px.");
            wInput.classList.add("rafa-invalid");
        } else { wInput.classList.remove("rafa-invalid"); }
        if (msgs.length > 0) {
            warning.innerHTML = msgs.join("<br>");
            warning.style.display = "block";
        } else { warning.style.display = "none"; }
    }

    wInput.addEventListener("input", checkWarnings);
    hInput.addEventListener("input", checkWarnings);
    checkWarnings();

    function applySize() {
        const newW = parseInt(wInput.value);
        const newH = parseInt(hInput.value);
        if (isNaN(newW) || isNaN(newH)) return;
        node.size[0] = Math.max(newW, minW);
        node.size[1] = Math.max(newH, minH);
        node.setDirtyCanvas(true, true);
        overlay.remove();
    }

    document.getElementById("rafa-size-apply").addEventListener("click", applySize);
    document.getElementById("rafa-size-cancel").addEventListener("click", () => overlay.remove());
    overlay.addEventListener("keydown", (e) => {
        if (e.key === "Enter") applySize();
        if (e.key === "Escape") overlay.remove();
    });
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) overlay.remove();
    });
}
