import msvcrt
import os
import pickle
import sys
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
from datetime import date, datetime, timedelta
from config import modo_prueba, modo_interactivo, AUSENCIAS, VACACIONES, FESTIVOS, HORARIO_NORMAL, HORARIO_REDUCIDO, URL_FICHAJE, USUARIO, VIGILIAS_NACIONALES, VARIACION_MIN, VARIACION_MAX, HORA_EJECUCION
from confirmacion import pedirConfirmacionUsuario
from filtrar_fichajes import obtenerFichajesRealizados
from logger_config import getLogger
from selenium.webdriver.chrome.service import Service

logger = getLogger()

def loginGuardar():
    logger.info("Inicio de login con Selenium")
    
    if not modo_prueba:
        load_dotenv()
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
  
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
        logger.debug("[Modo prueba] Selenium simulado: no se abre navegador ni se hacen acciones")

def cargarCookiesToken():
    with open("cookies.pkl", "rb") as f:
        cookies_list = pickle.load(f)
        
    cookies = {c['name']: c['value'] for c in cookies_list}
    
    with open("token_csrf.txt", "r") as f:
        token = f.read().strip()
        
    return cookies, token

def obtenerHoraVariada(hora_str, tipo=None, es_ultimo=False):
    """
    Devuelve una hora con variación aleatoria.
    
    - hora_str: hora base tipo "HH:MM"
    - tipo: "ClockIn" o "ClockOut"
    - es_ultimo: True si es el último fichaje del día
    """
    h, m = map(int, hora_str.split(":"))
    base = datetime.combine(date.today(), datetime.min.time()).replace(hour=h, minute=m)

    # Variación en minutos
    delta_minutos = random.randint(VARIACION_MIN, VARIACION_MAX)
    hora_variada = base + timedelta(minutes=delta_minutos)

    # Si es el último ClockOut → nunca antes de la hora base
    if es_ultimo and tipo == "ClockOut" and hora_variada < base:
        hora_variada = base

    return hora_variada.strftime("%H:%M")

def construirBody(hora):
    hoy = date.today()
    
    return {
        "clockDateTime": f"{hoy.isoformat()}T{hora}:00+02:00",
        "absenceReasonId": "",
        "lat": None,
        "lon": None
    }

def existeFichajeHoy(fichajes: list[str]) -> bool:
    hoy = date.today()
    for linea in fichajes:
        partes = linea.split('|')
        if len(partes) >= 1:
            fecha_str = partes[0].strip()
            try:
                fecha_datetime = datetime.strptime(fecha_str, "%d/%m/%Y %H:%M:%S")
                if fecha_datetime.date() == hoy:
                    return True
            except ValueError:
                continue
    return False

def prepararFichajes(horario, obtener_hora_variada, construir_body, logger):
    logger.info("Fichajes programados para hoy:")
    fichajes_previstos = []

    for i, (hora_str, tipo) in enumerate(horario):
        es_ultimo = (i == len(horario) - 1)
        hora_real = obtener_hora_variada(hora_str, tipo, es_ultimo)
        body = construir_body(hora_real)
        linea = f" - {tipo.upper()} → {hora_real} ({body['clockDateTime']})"
        print(linea)
        logger.info(linea)
        fichajes_previstos.append((hora_str, tipo, body))  # usamos hora_str para recalcular si hace falta

    return fichajes_previstos

def realizarFichajes():
    # Comprobar si existen cookies y token
	
    try:
        cookies, token = cargarCookiesToken()
    except FileNotFoundError:
        logger.error("No se encontraron cookies o token. Realizando login...")        
        loginGuardar()
        cookies, token = cargarCookiesToken()

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json",
        "requestverificationtoken": token,
        "x-requested-with": "XMLHttpRequest",
        "referer": URL_FICHAJE
    }

    hoy = date.today()
    
    fichajes = obtenerFichajesRealizados()
    
    es_laborable = hoy.weekday() < 5 #Lunes -s Viernes

    if not es_laborable:
        return
    
    if hoy in FESTIVOS:
        logger.warning(f"{hoy} es festivo. No se ficha.")
        return

    if hoy in AUSENCIAS:
        logger.warning(f"{hoy} es día de ausencia. No se ficha.")
        return

    if hoy in VACACIONES:
        logger.warning(f"{hoy} es día de vacaciones. No se ficha.")
        return

    if existeFichajeHoy(fichajes) and not modo_prueba:
        logger.warning("Ya existen fichajes de hoy.")
        return
    
    es_viernes = hoy.weekday() == 4	
    es_vigilia = hoy in VIGILIAS_NACIONALES
    es_vigilia_anticipada = (hoy + timedelta(days=1)) in VIGILIAS_NACIONALES

    if es_viernes or es_vigilia_anticipada:
        horario = HORARIO_REDUCIDO
        logger.warning(f"{hoy} es viernes o vigilia anticipada. Jornada reducida.")
    elif es_vigilia:        
        logger.warning(f"{hoy} es festivo nacional. No se ficha.")
        return
    else:
        horario = HORARIO_NORMAL
 
    fichajes_previstos = prepararFichajes(horario, obtenerHoraVariada, construirBody, logger)
          
    if not pedirConfirmacionUsuario(modo_interactivo, logger):        
        return  # o sys.exit(0), según tu lógica

    for i, (hora_str, tipo, body) in enumerate(fichajes_previstos):
        es_ultimo = (i == len(fichajes_previstos) - 1)
        hora_real = obtenerHoraVariada(hora_str, tipo, es_ultimo)
        body = construirBody(hora_real)
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
                logger.debug(f"[Modo prueba] Se simula POST a {URL_FICHAJE}/{tipo} con body: {body}")
				 
        except Exception as e:
            logger.error(f"ERROR al enviar fichaje {tipo} a las {hora_real}: {e}")
            print(f"⛔ ERROR al enviar fichaje {tipo} a las {hora_real}: {e} \n")
            time.sleep(random.randint(2, 5))

def tareaDiaria():
    logger.info("Ejecutando tarea diaria de fichaje...")
    realizarFichajes()
    logger.info("Tarea diaria finalizada.")


if __name__ == "__main__":    
    
    try:
        logger.info(f"Servicio iniciado. Se ejecutará la tarea diaria a las {date.today()}.")
       
        # if modo_prueba:
        #     tarea_diaria()
        # else:
        #     schedule.every().day.at(HORA_EJECUCION).do(tarea_diaria)
        
        tareaDiaria()
        
    except Exception as e:
        logger.exception(f"⛔ ERROR al enviar fichajes diarios: {e} \n")
        print(f"⛔ ERROR al enviar fichajes diarios: {e} \n")
   # finally:
        # if sys.stdin.isatty():
        #     input("Pulse una tecla para cerrar...")
        #     os.system("pause")
            
   # while True:
        #schedule.run_pending()
       # time.sleep(30)