# comfyui-rafa-worker — imagen para RunPod Serverless
# ----------------------------------------------------
# Deriva del worker oficial de RunPod y le añade tus custom nodes.
# RunPod construye esta imagen directamente desde GitHub (apuntando a este Dockerfile),
# así que ni tú ni yo necesitamos Docker en local.

FROM runpod/worker-comfyui:5.8.6-base

# Tus custom nodes propios (Resolution Preset, Claude Prompt Generator, Approval Gate, etc.).
# Se clonan en /comfyui/custom_nodes. Única dependencia externa: anthropic (su requirements.txt).
RUN git clone https://github.com/osuvense/comfyui-rafa-nodes \
        /comfyui/custom_nodes/comfyui-rafa-nodes \
 && pip install --no-cache-dir -r /comfyui/custom_nodes/comfyui-rafa-nodes/requirements.txt

# NOTAS (no tocar la imagen para esto):
#  - ANTHROPIC_API_KEY: se inyecta como variable de entorno del ENDPOINT en RunPod
#    (Settings -> Environment Variables), NUNCA horneada en la imagen.
#  - Modelos: NO se hornean aquí. Llegan por network volume en /runpod-volume/models/...
#    (checkpoints, loras/ZiT, loras/Flux, unet, vae, clip).
#  - Para fijar versión exacta de los nodos en el futuro, cambiar el git clone por
#    un commit concreto (git clone ... && git -C ... checkout <sha>).
