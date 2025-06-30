import logging
from logging.handlers import RotatingFileHandler
import os
import pickle
from dotenv import load_dotenv
import schedule
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import random
from datetime import date, timedelta
from config import modo_prueba, modo_interactivo, AUSENCIAS, VACACIONES, FESTIVOS, HORARIO_NORMAL, HORARIO_REDUCIDO, URL_FICHAJE, USUARIO, VIGILIAS_NACIONALES, VARIACION_MIN, VARIACION_MAX, HORA_EJECUCION
from confirmacion import mostrar_resumen_y_confirmar


# Configuración básica del logger
logger = logging.getLogger("fichajes_logger")
logger.setLevel(logging.DEBUG)

# Handler que escribe en archivo con rotación (máximo 5 archivos de 1MB)
handler = RotatingFileHandler("fichajes.log", maxBytes=1_000_000, backupCount=5, encoding='utf-8')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def login_y_guardar():
    logger.info("Inicio de login con Selenium")
    
    if not modo_prueba:
        load_dotenv()
        options = Options()
        driver = webdriver.Chrome(options=options)
        driver.get(URL_FICHAJE)

        time.sleep(5)
        input_usuario = driver.find_element(By.ID, "Input_Username")
        input_password = driver.find_element(By.ID, "Input_Password")

        input_usuario.send_keys(USUARIO)
        CONTRASENA = os.getenv("CONTRASENA") #guardada en el .env (NO SUBIR A GITHUB !!)
        input_password.send_keys(CONTRASENA)

        boton_login = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-primary.send-button"))
        )
        
        boton_login.click()
        time.sleep(10)

        cookies = driver.get_cookies()
        
        with open("cookies.pkl", "wb") as f:
            pickle.dump(cookies, f)

        token_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "__RequestVerificationToken"))
        )
        
        token = token_element.get_attribute("value")
        
        with open("token_csrf.txt", "w") as f:
            f.write(token)
            
        logger.info("Login completado. Cookies y token guardados.")
        driver.quit()
        
    else:
        logger.info("[Modo prueba] Selenium simulado: no se abre navegador ni se hacen acciones")

def cargar_cookies_token():
    with open("cookies.pkl", "rb") as f:
        cookies_list = pickle.load(f)
        
    cookies = {c['name']: c['value'] for c in cookies_list}
    
    with open("token_csrf.txt", "r") as f:
        token = f.read().strip()
        
    return cookies, token

def obtener_hora_variada(hora_str):
    h, m = map(int, hora_str.split(":"))
    
    delta = random.randint(VARIACION_MIN, VARIACION_MAX)
    total_min = h * 60 + m + delta
    h_final, m_final = divmod(total_min, 60)
    
    return f"{h_final:02}:{m_final:02}"

def construir_body(hora):
    hoy = date.today()
    
    return {
        "clockDateTime": f"{hoy.isoformat()}T{hora}:00+02:00",
        "absenceReasonId": "",
        "lat": None,
        "lon": None
    }

def realizar_fichajes():
    # Comprobar si existen cookies y token
	
    try:
        cookies, token = cargar_cookies_token()
    except FileNotFoundError:
        logger.warning("No se encontraron cookies o token. Realizando login...")        
        login_y_guardar()
        cookies, token = cargar_cookies_token()

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "referer": URL_FICHAJE
    }

    hoy = date.today()
    
    es_laborable = hoy.weekday() < 5
	
    if not es_laborable:
        return

    if hoy in FESTIVOS:
        logger.info(f"{hoy} es festivo. No se ficha.")
        return

    if hoy in AUSENCIAS:
        logger.info(f"{hoy} es día de ausencia. No se ficha.")
        return

    if hoy in VACACIONES:
        logger.info(f"{hoy} es día de vacaciones. No se ficha.")
        return

    es_viernes = hoy.weekday() == 4	
    es_vigilia = hoy in VIGILIAS_NACIONALES
    es_vigilia_anticipada = (hoy + timedelta(days=1)) in VIGILIAS_NACIONALES

    if es_viernes or es_vigilia_anticipada:
        horario = HORARIO_REDUCIDO
        logger.info(f"{hoy} es viernes o vigilia anticipada. Jornada reducida.")
    elif es_vigilia:        
        logger.info(f"{hoy} es festivo nacional. No se ficha.")
        return
    else:
        horario = HORARIO_NORMAL


    # ✅ Mostrar resumen y confirmar (modo interactivo desde configuración)
    fichajes_previstos = mostrar_resumen_y_confirmar(
        horario,
        modo_interactivo,
        logger,
        obtener_hora_variada,
        construir_body
    )
    
    for hora_str, tipo, body in fichajes_previstos:
        hora_real = obtener_hora_variada(hora_str)
        body = construir_body(hora_real)
        logger.info(f"{tipo} -> {hora_real} ({body['clockDateTime']})")        
        try:
            if not modo_prueba: 
                r = requests.post(
                    f"{URL_FICHAJE}/{tipo}",        
                    headers=headers,
                    cookies=cookies,
                    json=body)
				
                logger.info(f"Status: {r.status_code} | Respuesta: {r.text}")
            else:
                logger.info(f"[Modo prueba] Se simula POST a {URL_FICHAJE}/{tipo} con body: {body}")
				 
        except Exception as e:
            logger.error(f"Error al enviar fichaje {tipo} a las {hora_real}: {e}")
            time.sleep(random.randint(2, 5))


def tarea_diaria():
    logger.info("Ejecutando tarea diaria de fichaje...")
    realizar_fichajes()
    logger.info("Tarea diaria finalizada.")

if __name__ == "__main__":    
    logger.info(f"Servicio iniciado. Se ejecutará la tarea diaria a las {HORA_EJECUCION}.")
    tarea_diaria()  # Ejecuta la primera vez al arrancar para test rápido
    schedule.every().day.at(HORA_EJECUCION).do(tarea_diaria)
    while True:
        schedule.run_pending()
        time.sleep(30)