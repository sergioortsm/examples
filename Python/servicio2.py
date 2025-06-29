from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pickle
import requests

# --- PARTE 1: Login con Selenium y guardar cookies + token CSRF ---
def login_y_guardar():
    options = Options()
    # Quita comentario para headless si quieres sin ventana:
    # options.add_argument("--headless")

    driver = webdriver.Chrome(options=options)
    driver.get("https://telefichajes.zimaltec.es/")

    time.sleep(5)  # espera que cargue página login

    # Ajusta IDs si cambian, para usuario y password
    input_usuario = driver.find_element(By.ID, "Input_Username")
    input_password = driver.find_element(By.ID, "Input_Password")

    # Poner aquí usuario y contraseña reales
    input_usuario.send_keys("sorts@grupoactive.es")
    input_password.send_keys("999195")

    # Botón iniciar sesión por clase CSS
    boton_login = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-primary.send-button"))
    )
    boton_login.click()

    # Espera que cargue página principal tras login
    time.sleep(10)

    # Guardar cookies en archivo
    cookies = driver.get_cookies()
    with open("cookies.pkl", "wb") as f:
        pickle.dump(cookies, f)

    # Obtener token CSRF del input oculto
    token_element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "__RequestVerificationToken"))
    )
    token = token_element.get_attribute("value")

    with open("token_csrf.txt", "w") as f:
        f.write(token)

    print("Login completado. Cookies y token guardados.")
    driver.quit()


# --- PARTE 2: Usar cookies + token para hacer POST automático ---
def hacer_fichaje(fecha_hora_iso):
    session = requests.Session()
    with open("cookies.pkl", "rb") as f:
        cookies = pickle.load(f)
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))

    with open("token_csrf.txt", "r") as f:
        token = f.read().strip()

    url = "https://telefichajes.zimaltec.es/ClockIn"
    body = {
        "clockDateTime": fecha_hora_iso,
        "absenceReasonId": "",
        "lat": None,
        "lon": None
    }
    headers = {
        "RequestVerificationToken": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    response = session.post(url, json=body, headers=headers)
    print("Fichaje enviado:", fecha_hora_iso)
    print("Status:", response.status_code)
    print("Respuesta:", response.text)


if __name__ == "__main__":
    # Ejecutar primero login y guardar credenciales
    login_y_guardar()

    # Ejemplo de fichaje con fecha y hora ISO 8601
    # Cambia la fecha y hora por la que necesites enviar
    ejemplo_fecha = "2025-06-30T08:30:00+02:00"
    hacer_fichaje(ejemplo_fecha)
