# config.py
import json
from datetime import date, timedelta
import os
import re
import sys

# Qué validaciones hace
# Validación	Ejemplo que falla
# Formato hora	"830" en vez de "08:30"
# Tipo desconocido	"Start" en vez de "ClockIn"
# Hora duplicada	Dos "08:30"
# Dos seguidos de mismo tipo	("08:30", "ClockIn"), ("09:00", "ClockIn")
# Último no es ClockOut	termina con ClockIn

def validar_horarios(horario, nombre):
    formato_hora = re.compile(r"^\d{2}:\d{2}$")
    tipos_validos = {"ClockIn", "ClockOut"}
    
    horas_vistas = set()
    anterior_tipo = None

    for h, tipo in horario:
        if not formato_hora.match(h):
            raise ValueError(f"[{nombre}] Hora inválida: '{h}'")
        if tipo not in tipos_validos:
            raise ValueError(f"[{nombre}] Tipo inválido: '{tipo}'")
        if h in horas_vistas:
            raise ValueError(f"[{nombre}] Hora duplicada: '{h}'")
        horas_vistas.add(h)

        # Validación de alternancia In/Out
        if tipo == anterior_tipo:
            raise ValueError(f"[{nombre}] Secuencia inválida: '{tipo}' seguido de otro '{tipo}'")
        anterior_tipo = tipo

    if anterior_tipo != "ClockOut":
        raise ValueError(f"[{nombre}] La jornada debe terminar en 'ClockOut'")

def obtener_ruta_config(nombre_archivo="configuracion.json"):
    # 1. ¿Hay una variable de entorno?
    carpeta_base = os.getenv("RUTA_CONFIG")

    if carpeta_base is None:
        # 2. Si no hay, detectar si ejecuta como exe
        if getattr(sys, 'frozen', False):
            # Ejecutable (.exe) generado por PyInstaller
            carpeta_base = os.path.dirname(sys.executable)
        else:
            # Script Python (.py) normal
            carpeta_base = os.path.dirname(os.path.abspath(__file__))

    ruta_config = os.path.join(carpeta_base, nombre_archivo)

    if not os.path.exists(ruta_config):
        raise RuntimeError(f"⚠️ No se encontró '{nombre_archivo}' en:\n{ruta_config}")

    return ruta_config


with open(obtener_ruta_config(), "r", encoding="utf-8") as f:
    config = json.load(f)

try:
    RUTA_BASE = os.path.dirname(os.path.abspath(__file__))
    RUTA_CONFIG = obtener_ruta_config()
    
    with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
        data = json.load(f)
           
        FESTIVOS = set(date.fromisoformat(d) for d in data["FESTIVOS"])
        VIGILIAS_NACIONALES = set(date.fromisoformat(d) for d in data["VIGILIAS_NACIONALES"])
        AUSENCIAS = set(date.fromisoformat(d) for d in data.get("AUSENCIAS", []))
        VACACIONES = set(date.fromisoformat(d) for d in data.get("VACACIONES", []))
        HORARIO_NORMAL = [(h, tipo) for h, tipo in data["HORARIO_NORMAL"]]
        HORARIO_REDUCIDO = [(h, tipo) for h, tipo in data["HORARIO_REDUCIDO"]]

    # Cargar como set de fechas individuales:
    JORNADA_INTENSIVA = set()

    for rango in data.get("JORNADA_INTENSIVA", []):
        inicio = date.fromisoformat(rango["inicio"])
        fin = date.fromisoformat(rango["fin"])
        delta = (fin - inicio).days + 1  # +1 para incluir la fecha de fin        
        for i in range(delta):
            JORNADA_INTENSIVA.add(inicio + timedelta(days=i))
        
        validar_horarios(HORARIO_NORMAL, "HORARIO_NORMAL")
        validar_horarios(HORARIO_REDUCIDO, "HORARIO_REDUCIDO")

        VARIACION_MIN = data["VARIACION_MIN"]
        VARIACION_MAX = data["VARIACION_MAX"]
        HORA_EJECUCION = data["HORA_EJECUCION"]
        USUARIO = data.get("USUARIO")
        CONTRASENA = data.get("CONTRASENA")
        URL_FICHAJE = data.get("URL_FICHAJE")
        RUTA_LOG = data.get("RUTA_LOG")
                
        MODO_PRUEBA = data.get('MODO_PRUEBA', False)  # Por defecto False si no está
        MODO_INTERACTIVO = data.get('MODO_INTERACTIVO', True)
except FileNotFoundError:
    raise RuntimeError("⚠️ No se encontró configuracion.json")

    
     
