# worker/ — RunPod Serverless (TEMPORAL)

Andamiaje del **Hito 0 del agente v2**: `Dockerfile` que RunPod usa (vía integración
GitHub) para construir el worker de ComfyUI con estos custom nodes y servir los
workflows de Rafa como endpoint serverless.

- NO forma parte de la librería de nodos; vive aquí solo por pragmatismo.
- La `ANTHROPIC_API_KEY` se inyecta como variable de entorno del endpoint, nunca en la imagen.
- Los modelos llegan por network volume (`/runpod-volume/models/...`), no se hornean.
- **Se elimina cuando el agente esté operativo** (decisión de Rafa, 16/06/2026).
