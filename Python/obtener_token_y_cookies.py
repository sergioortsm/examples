from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import json
import os
import tempfile
import shutil

# Cambia este valor si tu perfil es otro (ej. "Profile 1", "Profile 2")
PERFIL_CHROME = "Profile 89"  # o "Profile 1"

def obtener_token_y_cookies():
    user = os.getlogin()
    chrome_data_path = f"C:/Users/{user}/AppData/Local/Google/Chrome/User Data"

    user = os.getlogin()
    origen = f"C:/Users/{user}/AppData/Local/Google/Chrome/User Data/Profile 89"
    destino = tempfile.mkdtemp()

    shutil.copytree(origen, destino, dirs_exist_ok=True)
   
    options = Options()
    options.add_argument(f"--user-data-dir={destino}")
    #options.add_argument(f"--user-data-dir={chrome_data_path}")
    options.add_argument(f"--profile-directory={PERFIL_CHROME}")
    #options.add_argument("--headless")  # Quitar si quieres ver la ventana
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")

    driver = webdriver.Chrome(options=options)
    driver.get("https://telefichajes.zimaltec.es")

    time.sleep(10)  # al inicio 5 #Espera por si tarda en cargar

    try:
        token = driver.find_element(By.NAME, "__RequestVerificationToken").get_attribute("value")
    except Exception as e:
        print("❌ No se pudo encontrar el token:", e)
        token = None

    cookies_dict = {}
    for cookie in driver.get_cookies():
        cookies_dict[cookie['name']] = cookie['value']

    driver.quit()

    if not token:
        print("❌ No se obtuvo el token. ¿Estás logueado en el perfil de Chrome?")
        return

    # Guardar en archivo
    resultado = {
        "token": token,
        "cookies": cookies_dict
    }

    with open("credenciales.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2)

    print("✅ Token y cookies guardadas en 'credenciales.json'")

if __name__ == "__main__":
    obtener_token_y_cookies()
