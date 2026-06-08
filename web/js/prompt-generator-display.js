// prompt-generator-display.js — display in-node del Claude Prompt Generator (Rafa)
// Parte del repo comfyui-rafa-nodes — github.com/osuvense/comfyui-rafa-nodes
//
// Muestra el PROMPT generado y el PENSAMIENTO (razonamiento) DENTRO del propio nodo
// ClaudePromptGenerator, sin necesidad de nodos "Show Text" externos. El backend ya empuja
// estos dos campos en el dict `ui` ({prompt:[...], razonamiento:[...]}); aquí solo se
// escuchan en onExecuted y se pintan en dos widgets de solo lectura.
//
// Patrón estándar de display in-node (cf. ShowText de pythongosssss): se crean los widgets
// una vez y se reutilizan; se marcan readOnly y serialize:false para no ensuciar el JSON
// del workflow guardado.

import { app } from "../../../scripts/app.js";
import { ComfyWidgets } from "../../../scripts/widgets.js";

const PREFIX = "rafa_display_";

app.registerExtension({
    name: "rafa.PromptGeneratorDisplay",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "ClaudePromptGenerator") return;

        function setText(node, name, text) {
            let w = node.widgets?.find((wd) => wd.name === name);
            if (!w) {
                w = ComfyWidgets["STRING"](node, name, ["STRING", { multiline: true }], app).widget;
                if (w.inputEl) {
                    w.inputEl.readOnly = true;
                    w.inputEl.style.opacity = "0.75";
                }
                // No persistir el texto de display en el workflow guardado.
                w.serialize = false;
            }
            w.value = text ?? "";
            return w;
        }

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            const joinField = (f) =>
                Array.isArray(f) ? f.join("") : (f ?? "");
            const prompt = joinField(message?.prompt);
            const razonamiento = joinField(message?.razonamiento);

            // Prompt primero (es lo que más se copia, texto limpio), pensamiento debajo.
            setText(this, PREFIX + "prompt", prompt);
            setText(this, PREFIX + "pensamiento", razonamiento);

            // Crecer el nodo si hace falta para que el texto sea legible (no encoge).
            requestAnimationFrame(() => {
                const sz = this.computeSize();
                if (sz[0] > this.size[0]) this.size[0] = sz[0];
                if (sz[1] > this.size[1]) this.size[1] = sz[1];
                this.onResize?.(this.size);
                app.graph.setDirtyCanvas(true, false);
            });
        };
    },
});
