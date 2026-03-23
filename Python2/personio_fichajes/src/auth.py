from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

try:
    from .config import Configuracion, obtener_directorio_runtime
except ImportError:
    from config import Configuracion, obtener_directorio_runtime


class AuthError(RuntimeError):
    pass


class AuthManager:
    def __init__(self, cfg: Configuracion, logger):
        self.cfg = cfg
        self.logger = logger
        cookies_path = Path(cfg.sesion_cookies_path)
        if not cookies_path.is_absolute():
            cookies_path = obtener_directorio_runtime() / cookies_path
        self.cookies_path = cookies_path

    def ensure_authenticated(self, session: requests.Session, force: bool = False):
        if not force and self._cargar_cookies(session) and self.sesion_valida(session):
            self.logger.info("Sesion reutilizada desde cookies persistidas.")
            return

        self.logger.info("Realizando login SSO en Personio...")
        self._login_sso_con_selenium(session)

        if not self.sesion_valida(session):
            raise AuthError("No se pudo validar la sesion tras login SSO.")

        self._guardar_cookies(session)
        self.logger.info("Autenticacion completada y cookies guardadas.")

    def sesion_valida(self, session: requests.Session) -> bool:
        hoy = date.today()
        inicio = hoy - timedelta(days=hoy.weekday())
        fin = inicio + timedelta(days=6)

        url = f"{self.cfg.base_url}/svc/attendance-bff/v1/timesheet/{self.cfg.employee_id}"
        params = {
            "start_date": inicio.isoformat(),
            "end_date": fin.isoformat(),
            "timezone": self.cfg.timezone,
        }

        try:
            resp = session.get(url, params=params, timeout=self.cfg.request_timeout_sec)
        except Exception as exc:
            self.logger.warning(f"No se pudo validar sesion: {exc}")
            return False

        if resp.status_code != 200:
            return False

        ctype = resp.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            return False

        try:
            data = resp.json()
        except Exception:
            return False

        return isinstance(data, dict) and "timecards" in data

    def _guardar_cookies(self, session: requests.Session):
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for c in session.cookies:
            data.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "secure": c.secure,
                }
            )

        with self.cookies_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _cargar_cookies(self, session: requests.Session) -> bool:
        if not self.cookies_path.exists():
            return False

        try:
            with self.cookies_path.open("r", encoding="utf-8") as f:
                cookies = json.load(f)

            for cookie in cookies:
                session.cookies.set(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/"),
                )
            return True
        except Exception as exc:
            self.logger.warning(f"No se pudieron cargar cookies persistidas: {exc}")
            return False

    def _chrome_debug_disponible(self) -> bool:
        import socket
        port = self.cfg.remote_debug_port
        if not port:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            return False

    def _crear_o_conectar_driver(self) -> Any:
        options = Options()
        if self._chrome_debug_disponible():
            port = self.cfg.remote_debug_port
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
            self.logger.info(f"Conectando a Chrome existente en puerto {port}.")
        else:
            if self.cfg.headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            if self.cfg.chrome_user_data_dir:
                options.add_argument(f"--user-data-dir={self.cfg.chrome_user_data_dir}")
                if self.cfg.chrome_profile_directory:
                    options.add_argument(f"--profile-directory={self.cfg.chrome_profile_directory}")
                self.logger.info(
                    f"Abriendo Chrome con perfil '{self.cfg.chrome_profile_directory or 'Default'}' "
                    f"desde {self.cfg.chrome_user_data_dir}."
                )
            else:
                self.logger.info("Abriendo nueva instancia de Chrome sin perfil especifico.")

        service = Service(ChromeDriverManager().install())
        return ChromeWebDriver(service=service, options=options)

    def navegar_con_sesion(self, session: requests.Session, url: str) -> tuple[Any, bool]:
        """Abre/conecta Chrome con sesion autenticada y navega a la URL indicada.

        Retorna (driver, conectado_a_existente).
        """
        conectado_a_existente = self._chrome_debug_disponible()
        driver = self._crear_o_conectar_driver()
        try:
            if conectado_a_existente:
                # Abrir pestaña nueva para no interrumpir la navegacion del usuario.
                driver.switch_to.new_window("tab")
                driver.get(url)
                self.logger.info("Pestaña nueva abierta en Chrome existente.")
            else:
                # Cargamos dominio base para poder inyectar cookies de session.
                driver.get(self.cfg.base_url)
                for c in session.cookies:
                    try:
                        driver.add_cookie(
                            {
                                "name": c.name,
                                "value": c.value,
                                "path": c.path or "/",
                                "secure": bool(c.secure),
                            }
                        )
                    except Exception as exc:
                        self.logger.debug(f"Cookie omitida '{c.name}': {exc}")
                driver.get(url)

            current = (driver.current_url or "").lower()
            if "login.personio.com" in current or "login.microsoftonline.com" in current:
                self.logger.info(
                    "Chrome redirigido a login. Completa SSO/MFA en la ventana; esperando acceso a attendance..."
                )
                self._esperar_login_exitoso(driver)

            self.logger.info(f"Chrome listo en URL: {driver.current_url}")
            return driver, conectado_a_existente
        except Exception:
            try:
                driver.quit()
            except Exception:
                pass
            raise

    def _login_sso_con_selenium(self, session: requests.Session):
        driver = None
        conectado_a_existente = False
        try:
            options = Options()

            if self._chrome_debug_disponible():
                port = self.cfg.remote_debug_port
                options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
                service = Service(ChromeDriverManager().install())
                driver = ChromeWebDriver(service=service, options=options)
                conectado_a_existente = True
                self.logger.info(f"Conectado a Chrome existente en puerto {port}.")
            else:
                if self.cfg.headless:
                    options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                if self.cfg.chrome_user_data_dir:
                    options.add_argument(f"--user-data-dir={self.cfg.chrome_user_data_dir}")
                    if self.cfg.chrome_profile_directory:
                        options.add_argument(f"--profile-directory={self.cfg.chrome_profile_directory}")
                    self.logger.info(
                        f"Abriendo Chrome con perfil '{self.cfg.chrome_profile_directory or 'Default'}' "
                        f"desde {self.cfg.chrome_user_data_dir}."
                    )
                service = Service(ChromeDriverManager().install())
                driver = ChromeWebDriver(service=service, options=options)

            login_url = (
                f"{self.cfg.base_url}/attendance/employee/{self.cfg.employee_id}"
                "?viewMode=weekly"
            )
            if not conectado_a_existente or "personio.com" not in driver.current_url.lower():
                driver.get(login_url)

            username = os.getenv("PERSONIO_SSO_USERNAME", "").strip()
            password = os.getenv("PERSONIO_SSO_PASSWORD", "").strip()

            if username:
                self._rellenar_si_existe(driver, (By.ID, "i0116"), username)
                self._click_si_existe(driver, (By.ID, "idSIButton9"))
                time.sleep(1)

            if password:
                self._rellenar_si_existe(driver, (By.ID, "i0118"), password)
                self._click_si_existe(driver, (By.ID, "idSIButton9"))

            if conectado_a_existente:
                self.logger.info("Chrome ya logueado, extrayendo cookies directamente.")
                self._esperar_login_exitoso(driver)
            else:
                self.logger.info(
                    "Completa MFA/consentimiento si aparece. Esperando confirmacion de sesion..."
                )
                self._esperar_login_exitoso(driver)

            for cookie in driver.get_cookies():
                session.cookies.set(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/"),
                )

        except Exception as exc:
            raise AuthError(f"Error durante login SSO: {exc}") from exc
        finally:
            # No cerrar un Chrome que ya estaba abierto antes de que el script lo usara.
            if driver is not None and not conectado_a_existente:
                driver.quit()

    def _esperar_login_exitoso(self, driver):
        deadline = time.time() + self.cfg.login_timeout_sec
        while time.time() < deadline:
            url = driver.current_url.lower()
            if "personio.com/attendance/employee" in url and "login.microsoftonline.com" not in url:
                return
            time.sleep(2)

        raise AuthError(
            "Timeout esperando login SSO/MFA. Revisa credenciales o completa MFA en ventana del navegador."
        )

    def _rellenar_si_existe(self, driver, locator: tuple[str, str], value: str):
        try:
            element = WebDriverWait(driver, 8).until(EC.presence_of_element_located(locator))
            element.clear()
            element.send_keys(value)
        except Exception:
            pass

    def _click_si_existe(self, driver, locator: tuple[str, str]):
        try:
            element = WebDriverWait(driver, 6).until(EC.element_to_be_clickable(locator))
            element.click()
        except Exception:
            pass
