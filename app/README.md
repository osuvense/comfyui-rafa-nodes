# App de Rafa (esqueleto, 08/11/2026)

Servidor en el Mac para usar desde el iPad. Diseño completo: `video/app_diseno.md` (knowledge del project).

Hoy: galería de lo último generado → abrir una imagen y ver su receta → «Preparar vídeo» (Claude, sin GPU: prompt de
vídeo y de audio, uno o varios tramos, editables) → «Animar en el pod» (sube la imagen al ComfyUI del pod y lanza la
plantilla `plantillas/animar.json`: V10 + MMAudio, con el prompt ya escrito) → el vídeo aparece en la página.

Se actualiza sola: perfiles (lee `perfiles_prompt/` del Mac en cada llamada), nodos (botón «Actualizar nodos» = `git pull`
+ recarga), plantillas (`python3 app/hacer_plantillas.py` las regenera desde `tools/video/wf.py`).

Variables: `RAFA_SALIDAS` (carpeta de salidas; por defecto el espejo del ICY), `RAFA_PERFILES_DIR`, `ANTHROPIC_API_KEY`,
`RAFA_COMFY_URL` (URL del ComfyUI del pod, p. ej. `https://<pod>-5555.proxy.runpod.net`).

Dependencias: `pip install fastapi uvicorn pillow numpy pyyaml anthropic`. Arranque:
`python3 -m uvicorn app.servidor:app --host 0.0.0.0 --port 8765` desde la raíz del repo; en el iPad, `http://<mac>:8765`.
Pendiente: app de macOS para arrancarla (preferencia de Rafa: nada de .command), panel de workers y pestañas.
