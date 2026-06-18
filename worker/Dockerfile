# comfyui-rafa-worker — imagen para RunPod Serverless
# ----------------------------------------------------
# Deriva del worker oficial de RunPod y le añade tus custom nodes.
# RunPod construye esta imagen directamente desde GitHub (apuntando a este Dockerfile).

FROM runpod/worker-comfyui:5.8.6-base

# Tus custom nodes propios (Resolution Preset, Claude Prompt Generator, Approval Gate, etc.).
# Se clonan en /comfyui/custom_nodes. Única dependencia externa: anthropic.
RUN git clone https://github.com/osuvense/comfyui-rafa-nodes \
        /comfyui/custom_nodes/comfyui-rafa-nodes \
 && pip install --no-cache-dir -r /comfyui/custom_nodes/comfyui-rafa-nodes/requirements.txt

# El volumen LoRAPilot guarda el text encoder en models/text_encoders/ (NO en models/clip/)
# y usa models/diffusion_models/. El extra_model_paths del worker base no mapea esas carpetas,
# así que CLIPLoader no encontraba qwen_3_4b ("clip_name not in []"). Lo ampliamos.
RUN printf '%s\n' \
  'runpod_worker_comfy:' \
  '  base_path: /runpod-volume' \
  '  checkpoints: models/checkpoints/' \
  '  clip: models/clip/' \
  '  clip_vision: models/clip_vision/' \
  '  configs: models/configs/' \
  '  controlnet: models/controlnet/' \
  '  embeddings: models/embeddings/' \
  '  loras: models/loras/' \
  '  upscale_models: models/upscale_models/' \
  '  vae: models/vae/' \
  '  unet: models/unet/' \
  '  text_encoders: models/text_encoders/' \
  '  diffusion_models: models/diffusion_models/' \
  > /comfyui/extra_model_paths.yaml

# NOTAS:
#  - ANTHROPIC_API_KEY: variable de entorno del ENDPOINT (secret), nunca en la imagen.
#  - Modelos: por network volume en /runpod-volume/models/... (no se hornean).
