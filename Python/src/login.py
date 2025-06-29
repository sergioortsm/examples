from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import pickle
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def login_y_guardar_cookies():
    options = Options()
    # No headless para que puedas ver el proceso (puedes activarlo después)
    # options.add_argument("--headless")  
    
    driver = webdriver.Chrome(options=options)
    driver.get("https://telefichajes.zimaltec.es/")

    # Espera que cargue la página de login (ajusta tiempos y elementos según tu web)
    time.sleep(5)

    # Aquí debes completar los pasos para hacer login automático, ejemplo:

    # Encontrar campos usuario y contraseña (ajusta selectores)
    input_usuario = driver.find_element(By.ID, "Input_Username")  # Cambia selector si hace falta
    input_password = driver.find_element(By.ID, "Input_Password")

    # Poner tus credenciales (no lo pongas en código en producción, usa variables seguras)
    input_usuario.send_keys("sorts@grupoactive.es")
    input_password.send_keys("999195")

    # Click en botón por clase CSS
    boton_login = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-primary.send-button"))
    )
    
    boton_login.click()

    # Espera a que termine login y cargue página principal
    time.sleep(10)

    # Guardar cookies a disco para usarlas luego
    cookies = driver.get_cookies()
    with open("cookies.pkl", "wb") as f:
        pickle.dump(cookies, f)
    
    print("Cookies guardadas en cookies.pkl")

    driver.quit()

if __name__ == "__main__":
    login_y_guardar_cookies()
