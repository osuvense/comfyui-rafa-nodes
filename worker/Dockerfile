# comfyui-rafa-worker — imagen para RunPod Serverless
# Deriva del worker oficial y añade tus custom nodes. RunPod la construye desde GitHub.

FROM runpod/worker-comfyui:5.8.6-base

# Custom nodes propios. Única dependencia externa: anthropic.
RUN git clone https://github.com/osuvense/comfyui-rafa-nodes \
        /comfyui/custom_nodes/comfyui-rafa-nodes \
 && pip install --no-cache-dir -r /comfyui/custom_nodes/comfyui-rafa-nodes/requirements.txt

# extra_model_paths alineado con la estructura del volumen LoRAPilot.
# CLAVE: el CLIPLoader de ComfyUI busca en la categoría "clip"; tu encoder (qwen_3_4b)
# está en models/text_encoders/, así que apuntamos "clip" ahí. Mantenemos también
# "text_encoders" y "diffusion_models" por compatibilidad.
RUN printf '%s\n' \
  'runpod_worker_comfy:' \
  '  base_path: /runpod-volume' \
  '  checkpoints: models/checkpoints/' \
  '  clip: models/text_encoders/' \
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

# NOTAS: ANTHROPIC_API_KEY como env del endpoint (secret). Modelos por network volume.
