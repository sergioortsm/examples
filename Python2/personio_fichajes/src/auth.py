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
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
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
                self.logger.warning(
                    "Chrome redirigido a login inesperadamente. Esperando SSO/MFA para acceder a attendance..."
                )
                self._esperar_login_exitoso(driver)

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
            # Incluso con Chrome existente, forzamos abrir attendance para validar sesion real.
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
        ultimo_click_login = 0.0
        ultimo_click_ms = 0.0
        estado_login_personio = {
            "signature": None,
            "url": None,
            "retries": 0,
        }
        while time.time() < deadline:
            url = driver.current_url.lower()
            if "personio.com/attendance/employee" in url and "login.microsoftonline.com" not in url:
                return

            # Si Personio muestra una pantalla intermedia de login (boton central),
            # intentamos pulsarlo para continuar al flujo SSO.
            if (time.time() - ultimo_click_login) >= 5:
                resultado_login = self._intentar_click_login_personio(
                    driver, url, estado_login_personio
                )
                if resultado_login in {"advanced", "stalled", "blocked"}:
                    ultimo_click_login = time.time()
                if resultado_login == "advanced":
                    time.sleep(1)
                    continue
                if resultado_login == "stalled":
                    time.sleep(1)
                    continue
                if resultado_login == "blocked" and estado_login_personio["retries"] >= 3:
                    raise AuthError(
                        "El boton OIDC de Personio no provoca transicion al flujo SSO. "
                        "Revisa si la pagina cambio o si requiere interaccion manual."
                    )
                if resultado_login == "blocked":
                    time.sleep(1)
                    continue

            # En pantallas de Microsoft, intentamos avanzar prompts comunes
            # (Siguiente, Iniciar sesion, Mantener la sesion iniciada, etc.).
            if (time.time() - ultimo_click_ms) >= 3 and self._intentar_avanzar_login_microsoft(driver, url):
                ultimo_click_ms = time.time()
                time.sleep(1)
                continue

            time.sleep(2)

        raise AuthError(
            "Timeout esperando login SSO/MFA. Revisa credenciales o completa MFA en ventana del navegador."
        )

    def _intentar_click_login_personio(self, driver, current_url: str, estado: dict[str, Any]) -> str:
        if "login.personio.com" not in current_url and "personio.com/login" not in current_url:
            self._reiniciar_estado_login_personio(estado)
            return "none"

        candidato = self._seleccionar_candidato_login_personio(driver)
        if not candidato:
            return "none"

        if estado["signature"] == candidato["signature"] and estado["url"] == current_url:
            estado["retries"] += 1
            self.logger.warning(
                f"Reclick ignorado sobre boton SSO sin cambio de pantalla: '{candidato['texto'] or candidato['combined'][:50]}'"
            )
            return "blocked"

        try:
            candidato["element"].click()
        except Exception:
            return "none"

        self.logger.info(
            f"Login SSO Personio: pulsando '{candidato['texto'] or candidato['combined'][:50]}'"
        )

        if self._esperar_transicion_login_personio(driver, current_url, candidato["element"]):
            self._reiniciar_estado_login_personio(estado)
            self.logger.info("Click de Personio confirmado con transicion al siguiente paso del SSO.")
            return "advanced"

        estado["signature"] = candidato["signature"]
        estado["url"] = current_url
        estado["retries"] = 1
        self.logger.warning(
            f"Boton SSO pulsado sin transicion inmediata: '{candidato['texto'] or candidato['combined'][:50]}'"
        )
        return "stalled"

    def _seleccionar_candidato_login_personio(self, driver) -> dict[str, Any] | None:
        selectores = (
            ("form[data-provider='oidc'] button[type='submit'][data-provider='oidc']", 200),
            ("form[data-provider='oidc'] button[type='submit']", 180),
            ("form[data-provider='oidc'] button", 160),
            ("button[data-provider='oidc']", 150),
            ("button, a[role='button'], input[type='submit'], a", 0),
        )
        candidatos: list[dict[str, Any]] = []
        for selector, base_score in selectores:
            for elem in driver.find_elements(By.CSS_SELECTOR, selector):
                candidato = self._analizar_candidato_login_personio(elem, selector, base_score)
                if candidato is not None:
                    candidatos.append(candidato)

        if not candidatos:
            return None

        candidatos.sort(
            key=lambda item: (
                item["score"],
                len(item["combined"]),
            ),
            reverse=True,
        )
        return candidatos[0]

    def _analizar_candidato_login_personio(
        self, elem, selector: str, base_score: int
    ) -> dict[str, Any] | None:
        try:
            if not elem.is_displayed() or not elem.is_enabled():
                return None

            texto = (elem.text or "").strip()
            texto_lower = texto.lower()
            aria = (elem.get_attribute("aria-label") or "").strip().lower()
            title = (elem.get_attribute("title") or "").strip().lower()
            valor = (elem.get_attribute("value") or "").strip().lower()
            provider = (elem.get_attribute("data-provider") or "").strip().lower()
            tipo = (elem.get_attribute("type") or "").strip().lower()
            tag = (elem.tag_name or "").strip().lower()
            combined = " ".join(
                part for part in [texto_lower, aria, title, valor, provider] if part
            ).strip()

            if not combined:
                return None

            score = base_score
            strong_markers = ("microsoft", "oidc", "unikal")
            login_markers = (
                "inicia sesion",
                "iniciar sesion",
                "iniciar sesión",
                "login",
                "log in",
                "sign in",
            )
            continue_markers = ("continuar", "continue")

            if tag == "button":
                score += 25
            elif tag == "input" and tipo == "submit":
                score += 20
            elif tag == "a":
                score -= 15

            if provider == "oidc":
                score += 80
            if tipo == "submit":
                score += 20
            if any(marker in combined for marker in strong_markers):
                score += 60
            if any(marker in combined for marker in login_markers):
                score += 20
            if "continuar con usuario unikal" in combined:
                score += 90
            elif any(marker in combined for marker in continue_markers):
                score += 5

            has_strong_marker = any(marker in combined for marker in strong_markers) or provider == "oidc"
            has_login_marker = any(marker in combined for marker in login_markers)
            ambiguous_continue_only = any(marker in combined for marker in continue_markers) and not (
                has_strong_marker or has_login_marker
            )

            if base_score == 0:
                if ambiguous_continue_only:
                    return None
                if tag == "a" and not has_strong_marker:
                    return None
                if not has_strong_marker and not has_login_marker:
                    return None

            description = (
                f"selector={selector}, tag={tag}, provider={provider or '-'}, texto={texto or '-'}"
            )
            signature = "|".join([selector, tag, provider, tipo, combined])
            return {
                "element": elem,
                "score": score,
                "combined": combined,
                "description": description,
                "signature": signature,                "texto": texto,            }
        except Exception:
            return None

    def _esperar_transicion_login_personio(self, driver, current_url: str, clicked_element) -> bool:
        try:
            WebDriverWait(driver, 4).until(
                lambda drv: self._ha_transicionado_login_personio(
                    drv, current_url, clicked_element
                )
            )
            return True
        except TimeoutException:
            return False

    def _ha_transicionado_login_personio(self, driver, current_url: str, clicked_element) -> bool:
        nueva_url = (driver.current_url or "").lower()
        if nueva_url != current_url:
            return True
        if "login.microsoftonline.com" in nueva_url:
            return True
        if driver.find_elements(By.ID, "i0116") or driver.find_elements(By.ID, "i0118"):
            return True
        try:
            return not clicked_element.is_displayed()
        except StaleElementReferenceException:
            return True

    def _reiniciar_estado_login_personio(self, estado: dict[str, Any]):
        estado["signature"] = None
        estado["url"] = None
        estado["retries"] = 0

    def _intentar_avanzar_login_microsoft(self, driver, current_url: str) -> bool:
        if "login.microsoftonline.com" not in current_url:
            return False

        username = os.getenv("PERSONIO_SSO_USERNAME", "").strip()
        password = os.getenv("PERSONIO_SSO_PASSWORD", "").strip()

        # Intento de autocompletado por si aparece de nuevo durante redirecciones.
        if username:
            self._rellenar_si_existe(driver, (By.ID, "i0116"), username)
        if password:
            self._rellenar_si_existe(driver, (By.ID, "i0118"), password)

        # Botones habituales del flujo Microsoft.
        botones_id = ["idSIButton9", "idSubmit_SAOTCC_Continue", "acceptButton", "btnSignin"]
        for button_id in botones_id:
            try:
                element = WebDriverWait(driver, 1).until(
                    EC.element_to_be_clickable((By.ID, button_id))
                )
                if element.is_displayed() and element.is_enabled():
                    element.click()
                    self.logger.info(f"SSO Microsoft: pulsado '{button_id}'.")
                    return True
            except Exception:
                continue

        # Fallback por texto visible en botones/enlaces.
        textos = (
            "iniciar sesion",
            "iniciar sesión",
            "sign in",
            "siguiente",
            "next",
            "si",
            "yes",
            "continuar",
            "continue",
        )
        for elem in driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit'], a[role='button'], a"):
            try:
                if not elem.is_displayed() or not elem.is_enabled():
                    continue

                texto = (elem.text or "").strip().lower()
                aria = (elem.get_attribute("aria-label") or "").strip().lower()
                value = (elem.get_attribute("value") or "").strip().lower()
                combinado = " ".join([texto, aria, value])

                if any(token in combinado for token in textos):
                    elem.click()
                    self.logger.info("SSO Microsoft: avanzado por texto visible.")
                    return True
            except Exception:
                continue

        return False

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
