import os
import sys
from PIL import Image

def obtenerImagen(relativa):
    
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Ejecutándose desde el .exe de PyInstaller
        base_path = sys._MEIPASS
    else:
        # Ejecutándose como .py normal
        base_path = os.path.abspath(os.path.dirname(__file__))

    return  Image.open(os.path.join(base_path, relativa))
