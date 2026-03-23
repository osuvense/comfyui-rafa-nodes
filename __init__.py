# __init__.py
# rafa-node-resize — github.com/osuvense/rafa-node-resize
#
# Nodos incluidos:
#   - ResolutionPreset: selector de resoluciones estándar FLUX/WAN con orientación
#
# La extensión JS (node-resize-panel.js) se carga automáticamente
# desde web/js/ sin necesitar registro aquí.

from .resolution_preset import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
