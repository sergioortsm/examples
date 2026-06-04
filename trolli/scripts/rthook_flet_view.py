# scripts/rthook_flet_view.py
# Runtime hook de PyInstaller para Trolli.
#
# El hook de build (hook-flet.py de flet_cli) ya incluye el cliente Flutter de
# Flet en el bundle bajo:
#
#   _internal/flet_desktop/app/flet/flet.exe   (+ DLLs, data/, ...)
#
# Sin embargo, en runtime flet_desktop.__init__.__locate_and_unpack_flet_view
# solo consulta FLET_VIEW_PATH o la cache ~\.flet\client\... y NUNCA mira
# directamente esa carpeta bundleada.
#
# Este hook resuelve eso: establece FLET_VIEW_PATH apuntando al cliente
# bundleado antes de que arranque el codigo Python, de forma que el exe sea
# completamente autocontenido (sin descargar nada en el primer arranque).
#
# Cuando el usuario ya tiene la cache local (~\.flet\client\...) esta variable
# no se sobreescribe; flet_desktop la prefiere sobre FLET_VIEW_PATH (paso 3
# de su logica de resolucion), por lo que no hay conflicto.

import os
import sys

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _bundled_flet = os.path.join(sys._MEIPASS, "flet_desktop", "app", "flet")
    if os.path.isdir(_bundled_flet) and not os.environ.get("FLET_VIEW_PATH"):
        os.environ["FLET_VIEW_PATH"] = _bundled_flet
