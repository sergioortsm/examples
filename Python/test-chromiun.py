import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import shutil
import tempfile

options = Options()
# options.add_argument("--headless")  # comenta o descomenta para probar

# driver = webdriver.Chrome(options=options)
# driver.get("https://www.google.com")
# print(driver.title)
# driver.quit()


user = os.getlogin()
origen = f"C:/Users/{user}/AppData/Local/Google/Chrome/User Data/Profile 89"
destino = tempfile.mkdtemp()

shutil.copytree(origen, destino, dirs_exist_ok=True)

options.add_argument(f"--user-data-dir={destino}")