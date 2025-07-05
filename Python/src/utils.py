import os
import sys
from PIL import Image

def obtenerImagen(relativa):
    
    if getattr(sys, 'frozen', False):
        # En EXE (PyInstaller)
        base_path = sys._MEIPASS
    else:
        # En ejecución normal (script .py)
        base_path = os.path.abspath(os.path.dirname(__file__))

    return  Image.open(os.path.join(base_path, relativa))
