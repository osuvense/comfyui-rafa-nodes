# comfyui-rafa-nodes

Custom nodes para ComfyUI. Categoría `rafa` en el menú de nodos.

## Instalación

```bash
cd /ruta/a/ComfyUI/custom_nodes
git clone https://github.com/osuvense/comfyui-rafa-nodes.git
```

En RunPod:
```bash
cd /workspace/runpod-slim/ComfyUI/custom_nodes
git clone https://github.com/osuvense/comfyui-rafa-nodes.git
```

Reiniciar ComfyUI tras la instalación.

---

## Nodo 1 — Tamaño del nodo (menú contextual)

Añade **"Tamaño del nodo..."** al menú contextual (click derecho) de cualquier nodo.

Permite fijar ancho y alto con valores numéricos exactos. Muestra el tamaño actual, el mínimo calculado por LiteGraph, y avisa si el valor introducido está por debajo del mínimo.

**Uso:** Click derecho sobre cualquier nodo → Tamaño del nodo...

- Muestra ancho y alto actual
- Muestra el tamaño mínimo calculado por LiteGraph para ese nodo
- Aviso naranja si el valor introducido está por debajo del mínimo (LiteGraph lo ignoraría)
- Al aplicar, clampea automáticamente al mínimo si el valor es menor
- Enter para aplicar, Escape o clic fuera para cerrar

**Notas:** Solo nodos — no afecta a grupos ni reroutes. Requiere ComfyUI con soporte de extensiones JS (frontend ≥ v1.x). Es puro JS, no requiere Python.

---

## Nodo 2 — Resolución Preset (Rafa)

Selector de resoluciones estándar para FLUX, ZIT y WAN. Outputs: `width` y `height` como INT, listos para conectar directamente a cualquier nodo que los necesite.

| Preset | Vertical | Horizontal |
|--------|----------|------------|
| FLUX — Retrato (1024×1024) | 1024 × 1024 | 1024 × 1024 |
| FLUX — Cuerpo entero (832×1216) | 832 × 1216 | 1216 × 832 |
| ZIT — Retrato (1024×1024) | 1024 × 1024 | 1024 × 1024 |
| ZIT — Cuerpo entero (832×1248) | 832 × 1248 | 1248 × 832 |
| ZIT 1536 — Retrato (1536×1536) | 1536 × 1536 | 1536 × 1536 |
| ZIT 1536 — Cuerpo entero (1248×1872) | 1248 × 1872 | 1872 × 1248 |
| WAN — 480p (480×832) | 480 × 832 | 832 × 480 |
| WAN — 720p (720×1280) | 720 × 1280 | 1280 × 720 |
| WAN — Cuadrado (1024×1024) | 1024 × 1024 | 1024 × 1024 |

**Uso:** Añadir nodo `Resolución Preset (Rafa)` → elegir preset y orientación → conectar `width` y `height` al nodo destino.

---

## Nodo 3 — Claude Prompt Generator (Rafa)

Genera prompts para **Z-Image Turbo** usando Claude API. Diseñado para trabajar con LoRAs de identidad y concepto sobre ZIT (encoder único Qwen3-4B).

**Características:**
- Toggles por personaje (Ceylan / Lexte / Yum) — activa los que necesites en cada generación
- Documentación de cada LoRA embebida — funciona sin archivos externos
- Carga captions de entrenamiento desde disco si están disponibles (vocabulario exacto del modelo)
- Claude decide qué trigger words incluir según la escena descrita
- Output: `prompt` (conectar al encoder) + `razonamiento` (explicación en español de las decisiones)

**Uso:**
1. Añadir nodo `Claude Prompt Generator (Rafa)`
2. Activar los personajes que aparecen en la escena
3. Escribir la descripción de la escena en español en el campo `scene`
4. Conectar la salida `prompt` al nodo de texto del encoder ZIT
5. Opcional: conectar `razonamiento` a un nodo Show Any para ver las decisiones

**Requisitos:**
- API key de Anthropic — configurar como variable de entorno `ANTHROPIC_API_KEY` o pegarla en el campo del nodo
- `pip install anthropic` (incluido en `requirements.txt`, se instala automáticamente en RunPod)

**Captions opcionales:** Si tienes los captions de entrenamiento en `/workspace/datasets/`, el nodo los carga automáticamente para mejorar la adherencia al vocabulario del modelo. Puedes cambiar la ruta base con la variable de entorno `RAFA_CAPTIONS_DIR`.

```bash
# Generar los archivos de captions desde los datasets
cat /workspace/datasets/CeylanV5/*.txt > /workspace/datasets/claude_context_ceylan.txt
cat /workspace/datasets/LestyV3/*.txt  > /workspace/datasets/claude_context_lexte.txt
cat /workspace/datasets/YumV3/*.txt    > /workspace/datasets/claude_context_yum.txt
```

---

## Notas generales

- Probado en ComfyUI Desktop v0.16.4 (Mac) y ComfyUI en RunPod (RTX 4090)
- El nodo de menú contextual es puro JS, no requiere Python
- Los nodos de resolución y prompt requieren reinicio completo de ComfyUI tras la instalación
