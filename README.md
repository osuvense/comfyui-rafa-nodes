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

Reiniciar ComfyUI tras la instalación. Los nodos con frontend JS (carpeta `web/`) requieren **reinicio completo del pod** al instalarse o actualizarse — no basta reiniciar solo el proceso de ComfyUI.

**Dependencias Python** (se instalan automáticamente vía `requirements.txt` en LoraPilot):
```
anthropic>=0.105.2
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

---

## Nodo 3 — Claude Prompt Generator (Rafa)

**Meganodo** de generación de prompts vía Claude API (refactor paradigm-shift-aware, jun 2026). Tres ejes de control:

**1. Modo:**

| Modo | Comportamiento |
|------|---------------|
| `LoRA solo` | Comportamiento clásico por toggles de LoRA. El paradigma lo da cada LoRA (pre-shift describe todo; post-shift enmascara). NO inyecta taste profile |
| `Improvisacion sin LoRA` | Ignora los toggles; el LLM monta el prompt desde una idea vaga + taste profile (si está activo). Para probar modelos a pelo |
| `LoRA + improvisacion` | Triggers de LoRA + taste profile combinados |

**2. Modelo destino** — cambia las reglas de prompting que se le dan al LLM:

| Target | Reglas |
|--------|--------|
| `Z-Image Turbo` | Prosa single-encoder Qwen3-4B |
| `Klein / FLUX.2` | Prosa single-encoder Qwen3-8B, CFG real, usa `negative` |
| `FLUX.1 legacy` | Dual encoder — rellena `clip_l` + `t5xxl` por separado |
| `Chroma1-HD` | Prosa + tags de calidad, usa `negative` |

**3. Taste profile** — ADN estético embebido (destilado de los captions de producción), activable. Solo actúa en los modos de improvisación; `taste_profile_override` permite sustituirlo puntualmente in-canvas sin tocar código.

**LoRAs soportadas:** `ceylan` / `lexte` / `yum` (pre-shift ZIT: el prompt describe todo con su vocabulario) y `ceyblan` (**post-shift**: su trigger absorbe la identidad → el nodo NO describe rasgos invariantes — calva, barriga, vello, bigote, pies, genitales — solo lo variable: escena, pose, ropa, luz, cámara). No combinar `ceyblan` con `ceylan` (mismo personaje).

**Outputs:** `prompt`, `razonamiento`, `clip_l`, `t5xxl`, `negative`. Los tres últimos solo se rellenan cuando el target los usa.

**Dials:** `nsfw` (explicit / suggestive / sfw), `framing` (auto / portrait / upper body / full body / genital close-up), `variants` (1–6, van al campo `razonamiento`), `creativity` (mapea a temperature), `seed` (cache buster: fijo = reutiliza cache sin gastar tokens; randomize/increment = fuerza variante nueva), `extra_directives`.

**Compatibilidad:** un workflow viejo carga con los defaults (`LoRA solo` + `Z-Image Turbo`) y se comporta idéntico al nodo original. Modelo de Claude por defecto: `claude-sonnet-4-6` (editable).

**Coste (10 jun 2026):** los LoRAs pre-shift llevan **caption digests embebidos** (destilado medido de su corpus de training: anclas léxicas con tasas, estructura del caption tipo, cobertura y sesgos) en lugar de cargar los captions completos de disco — se eliminó `claude_context_*.txt` y con ello ~8-45k tokens de input por llamada. Además el system prompt usa **prompt caching de Anthropic** (bloque estable cacheado 5 min → re-llamadas por seed a ~0.1x), hay fallback automático si el modelo depreca `temperature`, y el usage (in/out/cache) se imprime en consola por llamada.

---

## Nodo 3b — Prompt Approval Gate (Rafa)

Checkpoint humano entre el Prompt Generator y la inferencia, **con UI inline en el propio nodo** (sin ventana emergente). Resuelve el flujo: generar un prompt → revisarlo/editarlo → correr la inferencia solo cuando guste → generar imágenes en bucle con ese mismo prompt sin volver a llamar a la API.

| Modo | Comportamiento |
|------|---------------|
| `revisar y editar` | Pausa el workflow al llegar aquí: el prompt entrante cae en el campo `approved_text` del nodo, el nodo se resalta y su botón pasa a "⏸ APROBAR Y GENERAR (pausado)". Editas en el campo y pulsas el botón → continúa con el texto editado (1 imagen). |
| `produccion (bucle)` | NO pausa: emite directamente `approved_text` (el prompt ya aprobado). Con **Auto Queue** + seed del KSampler en `randomize`, genera en bucle sin re-pedir a la API. Con `approved_text` vacío corta la ejecución con un mensaje útil (ExecutionBlocker). |

**Reglas de oro del bucle:** seed del **generador** en `fixed` (si está en randomize, cada imagen re-pide a la API); seed del **KSampler** en `randomize` + Auto Queue. Conexión: `Generator → Gate → encoder/KSampler`. Inputs `negative`/`clip_l`/`t5xxl` pasan tal cual (en v1 solo se edita el prompt positivo).

Robustez: Cancel nativo de ComfyUI respetado (tick 0,3 s), refresh de página con pausa viva recupera el estado (GET `/rafa/prompt_gate/pending`), `execution_interrupted`/`error` limpian el estado. Nodo con `web/` → **reinicio completo del pod** al instalar/actualizar.

---

# Sistema de captioning post-shift (nodos 4 → 5 → 6)

Pipeline de captioneo para LoRA training bajo el **paradigma de enmascarado** (masked captioning): lo que el caption DESCRIBE no se aprende como identidad; lo que DEJA SIN DESCRIBIR queda anclado al trigger word. El sistema decide por observación qué es invariante en cada dataset (→ se enmascara) y qué varía (→ se describe), sin nada hardcodeado por personaje.

Flujo en un solo Queue: **Dataset Profiler** (analiza el dataset como conjunto, propone) → **Profile Review Pause** (el operador revisa/edita el perfil — la máquina propone, el operador decide) → **Caption Generator** (captiona imagen a imagen aplicando el perfil validado).

Conexiones: `dataset_profile` del Profiler ⇒ input del Pause ⇒ input `dataset_profile` del Captioner (convertir el widget a input: click derecho → Convert widget to input).

---

## Nodo 4 — Claude Dataset Profiler (Rafa)

Primer nodo del sistema: mira el dataset **como conjunto** y emite un Dataset Profile en Markdown (inglés) con: invariantes propuestos a enmascarar (Confident / Borderline con tasas de presencia), rasgos variables a describir, vocabulario canónico de escena (consistencia léxica) y reporte de curación (familias de frames de vídeo, sospechas de origen IA, overlays/watermarks, baja calidad).

**Diseño barato:** submuestreo determinista por stride uniforme (`sample_size`, 12 por defecto) + baja resolución (768 px lado largo). Una sola llamada API por dataset (~céntimos). Cada imagen va precedida de su `Filename:` real para que las referencias de curación sean mapeables.

**El perfil es una PROPUESTA:** el modelo marca lo dudoso como "operator must verify" y nunca finaliza decisiones de keep/discard. La revisión humana es el nodo 5.

**Parámetros:**

| Parámetro | Tipo | Default | Notas |
|-----------|------|---------|-------|
| `image_folder` | STRING | — | Carpeta del dataset (jpg, jpeg, png, webp, bmp) |
| `caption_mode` | dropdown | Identidad-persona | Debe coincidir con el del Captioner; determina qué clase de invariante se busca |
| `sample_size` | INT | 12 | Imágenes a muestrear (stride determinista) |
| `model` | STRING | claude-opus-4-8 | Editable |
| `temperature` | FLOAT | 0.20 | Opus 4.8/4.7 la deprecan → el nodo la omite solo si el modelo la rechaza (muestreo por `effort`) |
| `effort` | dropdown | high | `output_config.effort` de la API (low/medium/high/xhigh/max) |
| `thinking` | dropdown | adaptive | adaptive = default de producción (mejor razonamiento estado-vs-identidad); disabled = más rápido/barato |
| `prompt_caching` | BOOLEAN | True | Cachea el system prompt; surfacea `cache_w`/`cache_r` en el log |
| `output_profile_path` | STRING | — | Relleno → además escribe el perfil a fichero (.md) como documentación del dataset |
| `api_key` | STRING | — | Vacío = variable de entorno `ANTHROPIC_API_KEY` |

**Outputs:** `dataset_profile` (el perfil completo) y `log` (muestra, tokens, cache).

---

## Nodo 5 — Profile Review Pause (Rafa)

Checkpoint humano del sistema: se coloca **entre el Profiler y el Captioner** y pausa el workflow en un solo Queue para revisar/editar el Dataset Profile antes de que llegue al Captioner.

**Mecánica:** el backend empuja el perfil al navegador (WebSocket `rafa.profile_review`) y bloquea; el frontend (`web/js/profile-review-pause.js`) abre un modal con el perfil en un textarea editable; **Reanudar** devuelve el texto editado (POST `/rafa/profile_review/resume`) y desbloquea. El output `dataset_profile` emite la versión editada.

**Controles del modal:**
- **Reanudar** (o Ctrl+Enter) — envía el texto tal cual esté y reanuda el workflow
- **Cancelar workflow** — aborta la ejecución entera (el Captioner no corre, no gasta API)
- **Minimizar** (o Esc) — oculta el modal SIN perder la edición; queda un botón flotante "Revisión pendiente" para reabrirlo
- Click fuera del panel NO cierra (no se pierde una edición larga por un misclick)

**Robustez:**
- El Cancel nativo de ComfyUI también libera la pausa (check de interrupt cada 0.3 s)
- Refresh de página con pausa viva: el modal se reabre solo (GET `/rafa/profile_review/pending`)
- Dos nodos Pause en un workflow: las revisiones se encolan y se muestran una a una
- Si el workflow se interrumpe o falla, el modal se cierra solo

**Parámetros:**

| Parámetro | Tipo | Default | Notas |
|-----------|------|---------|-------|
| `dataset_profile` | STRING (input) | — | Conexión desde el Profiler |
| `enabled` | BOOLEAN | True | OFF = passthrough sin pausa (vía exprés / re-runs con perfil ya validado) |

Sin llamadas a la API de Claude: es un nodo de control puro. Al actualizarlo aplica el gotcha de nodos con `web/`: **reinicio completo del pod**.

---

## Nodo 6 — Claude Caption Generator (Rafa)

Captiona datasets de LoRA training con **Claude API con visión**, imagen a imagen a resolución plena, aplicando el paradigma de enmascarado. Recibe una carpeta, itera internamente y guarda un `.txt` por imagen (mismo nombre base). Sin dependencias de nodos externos de carga de imágenes.

**Formato de salida:** prosa pura en inglés (single-encoder Qwen3), rango de palabras configurable (35–80 por defecto), trigger word antepuesto con case canónico forzado por código (`_enforce_trigger`, no depende del modelo).

**`caption_mode`** (debe coincidir con el del Profiler):

| Modo | Qué enmascara | Qué describe |
|------|--------------|--------------|
| `Identidad-persona` | Identidad facial/corporal permanente del personaje (incl. genitales si es consistentemente la misma persona) | Escena, pose, ropa, luz, cámara, expresión |
| `Anatomía-sujeto-específico` | La anatomía permanente del sujeto (identidad: forma/tamaño característicos) | El ESTADO, por ser controlable: erección, posición del prepucio, agarre, ángulo, luz — descripción clínica |
| `Concepto-acción-pose` | El concepto/acción que se enseña (lo absorbe el trigger) | La anatomía (varía entre sujetos) y todo lo demás |
| `Estilo` | El estilo (lo absorbe el trigger) | El contenido de la imagen |
| `Custom` | Lo que digan `invariant_traits` + `extra_instructions` | — |

**Fuentes del perfil (precedencia):** `invariant_traits` y `canonical_vocabulary` rellenos MANDAN; vacíos + `dataset_profile` conectado → se extraen del perfil (solo invariantes **Confident**; los Borderline se reportan pero no se enmascaran solos).

**Reglas de observación embebidas:** el system prompt incluye las mitigaciones de observación de nivel imagen (14 reglas), p. ej. describir solo lo visible, no inventar acabado/esmalte de uñas (regla 14), estado ≠ identidad.

**Parámetros:**

| Parámetro | Tipo | Default | Notas |
|-----------|------|---------|-------|
| `image_folder` | STRING | — | Carpeta del dataset |
| `trigger_word` | STRING | — | Se antepone a cada caption con su case exacto |
| `caption_mode` | dropdown | Identidad-persona | Ver tabla |
| `nsfw` | BOOLEAN | True | Mode-aware: difiere siempre a `invariant_traits` (en Identidad-persona los genitales siguen enmascarados aunque esté ON) |
| `min_words` / `max_words` | INT | 35 / 80 | Rango de palabras post-shift |
| `model` | STRING | claude-opus-4-8 | Editable |
| `temperature` | FLOAT | 0.20 | Opus 4.8/4.7 la deprecan → se omite automáticamente si el modelo la rechaza |
| `max_images` | INT | 0 | 0 = todas; 1 = modo prueba |
| `dataset_profile` | STRING | — | Perfil del Profiler (conexión nodo a nodo vía Pause, o pegado) |
| `invariant_traits` | STRING | — | Si está relleno, MANDA sobre el perfil |
| `canonical_vocabulary` | STRING | — | Si está relleno, MANDA sobre el perfil |
| `extra_instructions` | STRING | — | Instrucciones por sesión |
| `effort` | dropdown | high | Igual que el Profiler |
| `thinking` | dropdown | adaptive | Default de producción (mejor observación; la alucinación de detalle fino la corta la regla 14) |
| `prompt_caching` | BOOLEAN | True | El system prompt es idéntico en todo el batch → se cobra una vez |
| `output_dir` | STRING | — | Vacío = misma carpeta que las imágenes |
| `save_captions` | BOOLEAN | True | False = preview sin escribir |
| `skip_existing` | BOOLEAN | True | Salta imágenes con `.txt` existente — permite reanudar batches |
| `api_key` | STRING | — | Vacío = variable de entorno `ANTHROPIC_API_KEY` |

**Outputs:** `last_caption` (conectar a Show Text para preview) y `log` (estado por imagen OK/SKIP/ERROR + tokens + cache).

---

## Notas generales

- Probado en ComfyUI Desktop v0.16.4 (Mac) y ComfyUI en RunPod (RTX 4090 / RTX 5090)
- El nodo de menú contextual es puro JS, no requiere Python
- Los nodos Python requieren reinicio de ComfyUI tras la instalación; los que tocan `web/` (nodos 1, 3b y 5), **reinicio completo del pod**
- `ANTHROPIC_API_KEY` debe configurarse como **secret** en la plantilla de RunPod (no como variable normal)
- SDK mínimo: `anthropic>=0.105.2` (soporte nativo de `output_config`/`thinking`; con SDKs viejos los nodos hacen fallback vía `extra_body`)
- **Opus 4.8/4.7 deprecan `temperature`** (la API devuelve 400): los nodos lo detectan, reintentan sin ella y no la reenvían el resto del batch — el muestreo se controla con `effort`
- Gotcha para futuros nodos con side-effect de escritura: declarar `IS_CHANGED` (los nodos 4, 5 y 6 usan `NaN` para forzar re-ejecución en cada Queue) o ComfyUI los cachea y no los re-ejecuta
