# comfyui-rafa-nodes

Custom nodes para ComfyUI. Categoría `rafa` en el menú de nodos.

## Instalación

```bash
cd /ruta/a/ComfyUI/custom_nodes
git clone https://github.com/osuvense/comfyui-rafa-nodes.git
```

En RunPod (LoraPilot):
```bash
cd /workspace/apps/comfy/custom_nodes
git clone https://github.com/osuvense/comfyui-rafa-nodes.git
```

Reiniciar ComfyUI tras la instalación. Para nodos nuevos añadidos después del arranque del pod, reinicio completo del pod.

**Dependencias Python** (se instalan automáticamente vía `requirements.txt` en LoraPilot):
```
anthropic
```

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
- Variable de entorno `ANTHROPIC_API_KEY` configurada como secret en RunPod
- `pip install anthropic` (incluido en `requirements.txt`)

**Captions opcionales:** Si tienes los captions de entrenamiento en `/workspace/datasets/`, el nodo los carga automáticamente. Ruta configurable con `RAFA_CAPTIONS_DIR`.

```bash
cat /workspace/datasets/CeylanV5/*.txt  > /workspace/datasets/claude_context_ceylan.txt
cat /workspace/datasets/LexteV3/*.txt   > /workspace/datasets/claude_context_lexte.txt
cat /workspace/datasets/YumV3/*.txt     > /workspace/datasets/claude_context_yum.txt
```

---

## Nodo 4 — Claude Caption Generator (Rafa)

Genera captions para datasets de LoRA training usando **Claude API con visión** (multimodal).

Recibe una ruta de carpeta como input, itera internamente sobre todas las imágenes, y guarda un `.txt` por imagen con el mismo nombre base. Sin dependencias de nodos externos de carga de imágenes.

**Características:**
- Genérico — funciona para cualquier personaje o concepto, sin nada hardcodeado
- Formatos: FLUX Dual (keywords + prosa) / ZIT Prose (prosa directa) / Custom
- `skip_existing` — salta imágenes ya captionadas sin gastar tokens, permite reanudar batches
- Model string libre y editable — sin dropdowns hardcodeados, actualizable sin tocar código
- Instrucciones por sesión (`extra_instructions`) sin modificar el system prompt base
- Log detallado: estado por imagen (OK / SKIP / ERROR) y tokens consumidos

**Outputs:**
- `last_caption` — el último caption generado (conectar a Show Text para preview)
- `log` — una línea por imagen con estado y tokens

**Uso:**
1. Añadir nodo `Claude Caption Generator (Rafa)`
2. Escribir la ruta de la carpeta en `image_folder`
3. Configurar `trigger_word` y `subject_description` para el personaje o concepto
4. Elegir `format`, `nsfw`, `caption_length` y `model`
5. Conectar `last_caption` y `log` a nodos Show Text para monitorizar
6. Ejecutar — el nodo procesa todas las imágenes de la carpeta en secuencia

**Lógica del system_prompt:**

| Situación | Comportamiento |
|-----------|---------------|
| `system_prompt` vacío + FLUX Dual | Usa DEFAULT_PROMPT_FLUX + modificadores |
| `system_prompt` vacío + ZIT Prose | Usa DEFAULT_PROMPT_ZIT + modificadores |
| `system_prompt` relleno + cualquier format | Usa el custom como base + modificadores |
| `format = Custom` + `system_prompt` vacío | Error en log, no llama a API |

Los modificadores `nsfw`, `caption_length`, `subject_description` y `extra_instructions` se añaden siempre al final, independientemente del prompt base usado.

**Parámetros:**

| Parámetro | Tipo | Default | Notas |
|-----------|------|---------|-------|
| `image_folder` | STRING | — | Ruta de la carpeta. Procesa jpg, jpeg, png, webp, bmp |
| `trigger_word` | STRING | — | Se antepone a cada caption automáticamente |
| `subject_description` | STRING | — | Descripción libre del sujeto; Claude la usa para identificar al personaje |
| `format` | dropdown | FLUX Dual | FLUX Dual / ZIT Prose / Custom |
| `nsfw` | BOOLEAN | True | Activa instrucciones explícitas de contenido adulto |
| `caption_length` | dropdown | medium | short / medium / long |
| `model` | STRING | claude-sonnet-4-6 | Editable directamente; actualizar cuando salgan modelos nuevos |
| `temperature` | FLOAT | 0.20 | Valor estable probado; no subir de 0.40 para captioning |
| `extra_instructions` | STRING | — | Instrucciones por sesión sin tocar el system prompt |
| `system_prompt` | STRING | — | Vacío = usa default del formato. Relleno = base custom |
| `output_dir` | STRING | — | Vacío = misma carpeta que las imágenes |
| `save_captions` | BOOLEAN | True | False = preview sin escribir a disco |
| `skip_existing` | BOOLEAN | True | Salta imágenes con `.txt` ya existente |
| `api_key` | STRING | — | Vacío = usa variable de entorno `ANTHROPIC_API_KEY` |

**Requisitos:**
- Variable de entorno `ANTHROPIC_API_KEY` configurada como secret en RunPod, o pegada en el campo `api_key`
- `pip install anthropic` (incluido en `requirements.txt`)

---

## Notas generales

- Probado en ComfyUI Desktop v0.16.4 (Mac) y ComfyUI en RunPod (RTX 4090)
- El nodo de menú contextual es puro JS, no requiere Python
- Los nodos Python requieren reinicio completo de ComfyUI tras la instalación
- `ANTHROPIC_API_KEY` debe configurarse como **secret** en la plantilla de RunPod (no como variable normal)
