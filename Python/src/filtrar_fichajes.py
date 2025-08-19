import subprocess
import sys
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import os
from config import URL_FICHAJE, USUARIO


def obtenerFichajesRealizados():
    
    if getattr(sys, 'frozen', False):
        # En .exe generado con PyInstaller
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    
    driver_path = os.path.join(base_path, "chromedriver.exe")    
    dotenv_path = os.path.join(base_path, ".env")
    
    load_dotenv(dotenv_path)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(executable_path=driver_path)
    service.creation_flags = subprocess.CREATE_NO_WINDOW  # Oculta ventana en Windows
    service.log_output = open(os.devnull, "w")

    driver = webdriver.Chrome(options=options, service=service)
    driver.get(URL_FICHAJE)
   
    time.sleep(5)
    input_usuario = driver.find_element(By.ID, "Input_Username")
    input_password = driver.find_element(By.ID, "Input_Password")

    input_usuario.send_keys(USUARIO)
    CONTRASENA = os.getenv("CONTRASENA","") #guardada en el .env (NO SUBIR A GITHUB !!)
    input_password.send_keys(CONTRASENA)

    boton_login = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-primary.send-button"))
    )

    boton_login.click() # Hacer clic botón de Login
    time.sleep(10)
   
    boton_listado = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), 'Listado fichajes')]]"))
    )

    # Hacer clic botón de listado fichajes de la web
    boton_listado.click()
    time.sleep(5)

    # Obtener filas de la tabla
    filas = driver.find_elements(By.CSS_SELECTOR, "tbody tr")

    fichajes_realizados = []

    for fila in filas:
        columnas = fila.find_elements(By.TAG_NAME, "td")
        if len(columnas) >= 4:
            fecha_hora = columnas[0].text
            tipo = columnas[1].text        
            linea = f"{fecha_hora} | {tipo} "
            fichajes_realizados.append(linea)
            #print(f"{fecha_hora} | {tipo} | {origen} | {motivo}")

    # Cierra el navegador si no quieres seguir
    driver.quit()
    
    return fichajes_realizados