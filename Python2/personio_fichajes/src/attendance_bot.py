from __future__ import annotations

import re
import time
from datetime import date

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


_SELECTOR_FILA = 'div[role="row"][data-test-id="timesheet-timecard"]'
_MESES_ES = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}


class AttendanceBot:
    def __init__(self, driver, cfg, logger):
        self.driver = driver
        self.cfg = cfg
        self.logger = logger
        self.wait = WebDriverWait(driver, 20)

    def _parse(self, hhmm: str) -> tuple[str, str]:
        h, m = hhmm.split(":")
        return h, m

    def _normalizar_clave_dia(self, clave: str) -> str:
        return (clave or "").strip().lower().replace("é", "e").replace("á", "a")

    def _normalizar_texto(self, texto: str) -> str:
        return " ".join((texto or "").strip().lower().split())

    def _es_valor_cero_horas(self, texto: str) -> bool:
        t = self._normalizar_texto(texto)
        return t in {
            "0",
            "0h",
            "0 h",
            "0m",
            "0 m",
            "0h 0m",
            "0 h 0 m",
            "00:00",
            "00",
            "0:00",
        }

    def _evaluar_fila_rellenada(self, fila) -> tuple[bool, str]:
        # 1) Si la fila indica estado aprobado/confirmado, no se debe tocar.
        texto_fila = self._normalizar_texto(fila.text)
        if any(palabra in texto_fila for palabra in ("aprobada", "approved", "confirmada", "confirmed")):
            return True, "estado_aprobado"

        # 2) Si hay celdas de rango con horas distintas de cero, ya tiene imputacion.
        try:
            ranges = fila.find_elements(By.CSS_SELECTOR, 'time[data-test-id="range-cell-time"]')
            for r in ranges:
                val = self._normalizar_texto(r.text)
                if val and not self._es_valor_cero_horas(val):
                    return True, "rango_horario"
        except Exception:
            pass

        # 3) Si tracked-vs-target muestra tiempo real > 0h, ya esta rellenado.
        try:
            tracked = fila.find_element(By.CSS_SELECTOR, '[data-test-id="tracked-vs-target-area"]')
            times = tracked.find_elements(By.CSS_SELECTOR, "time")
            if times:
                actual = self._normalizar_texto(times[0].text)
                if actual and not self._es_valor_cero_horas(actual):
                    return True, "tracked_horas"
        except Exception:
            pass

        return False, "sin_horas"

    def _horario_para_dia(self, nombre: str) -> list[dict] | None:
        nombre_norm = self._normalizar_clave_dia(nombre)
        ms = self._parse(self.cfg.morning_start)
        me = self._parse(self.cfg.morning_end)
        as_ = self._parse(self.cfg.afternoon_start)
        ae = self._parse(self.cfg.afternoon_end)
        fs = self._parse(self.cfg.friday_start)
        fe = self._parse(self.cfg.friday_end)

        lun_jue = [
            {"tipo": "trabajo", "inicio": ms, "fin": me},
            {"tipo": "descanso", "inicio": me, "fin": as_},
            {"tipo": "trabajo", "inicio": as_, "fin": ae},
        ]
        vie = [{"tipo": "trabajo", "inicio": fs, "fin": fe}]
        return {
            "lun": lun_jue,
            "mar": lun_jue,
            "mie": lun_jue,
            "mié": lun_jue,
            "jue": lun_jue,
            "vie": vie,
        }.get(nombre_norm)

    def _obtener_time_fecha(self, fila):
        selectores = [
            'div[class*="DayCell-module__cell"] time[datetime]',
            'div[role="gridcell"] time[datetime]',
            'time[datetime]',
        ]
        for selector in selectores:
            elementos = fila.find_elements(By.CSS_SELECTOR, selector)
            if elementos:
                return elementos[0]
        raise RuntimeError("No se encontro time[datetime] para la fecha de la fila")

    def _resolver_fecha_visible(self, label: str, fecha_html: date | None) -> date | None:
        texto = self._normalizar_texto(label).replace(".", "")
        match = re.match(r"^(\d{1,2})\s+([a-zñ]+)$", texto)
        if not match:
            return fecha_html

        dia = int(match.group(1))
        mes_txt = match.group(2)[:3]
        mes = _MESES_ES.get(mes_txt)
        if mes is None:
            return fecha_html

        if fecha_html is None:
            try:
                return date(date.today().year, mes, dia)
            except ValueError:
                return None

        candidatos: list[date] = []
        for year in (fecha_html.year - 1, fecha_html.year, fecha_html.year + 1):
            try:
                candidatos.append(date(year, mes, dia))
            except ValueError:
                pass

        if not candidatos:
            return fecha_html

        return min(candidatos, key=lambda candidata: abs((candidata - fecha_html).days))

    def _construir_info_fila(self, fila) -> dict:
        nombre = fila.find_element(By.CSS_SELECTOR, "span[aria-hidden='true']").text.strip().lower()
        time_el = self._obtener_time_fecha(fila)
        label = time_el.text.strip()
        fecha_html_str = time_el.get_attribute("datetime") or ""
        try:
            fecha_html = date.fromisoformat(fecha_html_str)
        except ValueError:
            fecha_html = None
        fecha = self._resolver_fecha_visible(label, fecha_html)
        day_id = fila.get_attribute("data-attendance-day-id")
        tiene_horas, motivo_relleno = self._evaluar_fila_rellenada(fila)

        return {
            "nombre": nombre,
            "label": label,
            "day_id": day_id,
            "fecha": fecha,
            "fecha_html": fecha_html,
            "tiene_horas": tiene_horas,
            "motivo_relleno": motivo_relleno,
        }

    def _obtener_filas(self) -> list[dict]:
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SELECTOR_FILA)))
        except Exception as exc:
            url = (self.driver.current_url or "").lower()
            if "login.personio.com" in url or "login.microsoftonline.com" in url:
                raise RuntimeError(
                    "No se pudo acceder a attendance: Chrome sigue en login SSO/MFA."
                ) from exc
            raise
        elementos = self.driver.find_elements(By.CSS_SELECTOR, _SELECTOR_FILA)
        dias: list[dict] = []

        for el in elementos:
            if el.get_attribute("data-is-weekend") == "true":
                continue
            if el.get_attribute("data-is-off-day") == "true":
                continue

            try:
                dias.append(self._construir_info_fila(el))
            except Exception as exc:
                self.logger.warning(f"Fila omitida al escanear: {exc}")
        return dias

    def _obtener_fila_por_fecha(self, fecha_obj: date) -> dict | None:
        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SELECTOR_FILA)))
        except Exception as exc:
            url = (self.driver.current_url or "").lower()
            if "login.personio.com" in url or "login.microsoftonline.com" in url:
                raise RuntimeError(
                    "No se pudo acceder a attendance: Chrome sigue en login SSO/MFA."
                ) from exc
            raise

        fecha_obj_txt = fecha_obj.isoformat()
        filas = self.driver.find_elements(By.CSS_SELECTOR, _SELECTOR_FILA)
        for fila in filas:
            try:
                if fila.get_attribute("data-is-weekend") == "true":
                    continue
                if fila.get_attribute("data-is-off-day") == "true":
                    continue

                info = self._construir_info_fila(fila)
                if info.get("fecha") != fecha_obj:
                    continue

                self.logger.info(
                    "Fila localizada por fecha visible="
                    f"{fecha_obj_txt}: label_visible='{info['label']}', "
                    f"datetime_html={info.get('fecha_html')}"
                )

                return info
            except Exception as exc:
                self.logger.warning(f"Fila omitida al localizar fecha {fecha_obj_txt}: {exc}")

        return None

    def _fila_el(self, day_id: str):
        return self.driver.find_element(By.CSS_SELECTOR, f'div[data-attendance-day-id="{day_id}"]')

    def _fila_existe(self, day_id: str) -> bool:
        return bool(self.driver.find_elements(By.CSS_SELECTOR, f'div[data-attendance-day-id="{day_id}"]'))

    def _describir_elemento(self, element) -> str:
        try:
            rect = self.driver.execute_script(
                "const r = arguments[0].getBoundingClientRect();"
                "return {x: r.x, y: r.y, width: r.width, height: r.height};",
                element,
            )
        except Exception:
            rect = None

        atributos = {
            "tag": None,
            "text": None,
            "contenteditable": None,
            "aria-disabled": None,
            "aria-valuetext": None,
            "class": None,
            "enabled": None,
            "displayed": None,
            "rect": rect,
        }
        try:
            atributos["tag"] = element.tag_name
            atributos["text"] = (element.text or "").strip()
            atributos["contenteditable"] = element.get_attribute("contenteditable")
            atributos["aria-disabled"] = element.get_attribute("aria-disabled")
            atributos["aria-valuetext"] = element.get_attribute("aria-valuetext")
            atributos["class"] = element.get_attribute("class")
            atributos["enabled"] = element.is_enabled()
            atributos["displayed"] = element.is_displayed()
        except Exception:
            pass
        return str(atributos)

    def _click_elemento(self, element, descripcion: str) -> None:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        except Exception:
            pass

        try:
            WebDriverWait(self.driver, 5).until(lambda d: element.is_enabled())
        except Exception:
            pass

        try:
            element.click()
            return
        except Exception as exc:
            self.logger.warning(
                f"Click normal fallo en {descripcion}: {exc}. Detalle: {self._describir_elemento(element)}"
            )

        try:
            self.driver.execute_script("arguments[0].click();", element)
            return
        except Exception as exc:
            self.logger.warning(
                f"Click JS fallo en {descripcion}: {exc}. Detalle: {self._describir_elemento(element)}"
            )
            raise

    def _set_spinbutton(self, element, valor: str) -> None:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        except Exception:
            pass

        try:
            element.click()
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except Exception:
                pass

        time.sleep(0.08)
        ActionChains(self.driver).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        time.sleep(0.05)
        try:
            element.send_keys(valor)
        except Exception as exc:
            self.logger.warning(
                "Fallo al hacer send_keys en spinbutton: "
                f"valor='{valor}', detalle={self._describir_elemento(element)}, error={exc}"
            )
            raise
        time.sleep(0.15)

    def _rellenar_time_group(self, form, test_id: str, hora: tuple[str, str]) -> None:
        grp = form.find_element(By.CSS_SELECTOR, f'[data-test-id="{test_id}"]')
        sbs = grp.find_elements(By.CSS_SELECTOR, 'span[role="spinbutton"][contenteditable="true"]')
        if len(sbs) < 2:
            candidatos = grp.find_elements(By.CSS_SELECTOR, 'span[role="spinbutton"]')
            self.logger.warning(
                f"Grupo {test_id} no editable: total_spinbuttons={len(candidatos)}, detalles="
                + " | ".join(self._describir_elemento(sb) for sb in candidatos)
            )
            raise RuntimeError(f"Grupo {test_id} no editable o incompleto")
        self._set_spinbutton(sbs[0], hora[0])
        self._set_spinbutton(sbs[1], hora[1])

    def _form(self, aria_controls: str):
        return WebDriverWait(self.driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, f'//div[@id="{aria_controls}"]//form[@data-test-id="time-entry-form"]')
            )
        )

    def _rellenar_dia(self, info: dict) -> bool:
        nombre = info["nombre"]
        horario = self._horario_para_dia(nombre)
        if not horario:
            self.logger.info(f"Sin horario para '{nombre}' ({info['label']}), se omite.")
            return False

        if not self._fila_existe(info["day_id"]):
            self.logger.info(
                f"La fila de {info['label']} ya no esta visible tras refresco de UI; se omite."
            )
            return False

        fila = self._fila_el(info["day_id"])
        self.logger.info(f"Abriendo dia {info['label']} ({nombre})")
        try:
            celda_fecha = fila.find_element(By.CSS_SELECTOR, 'div[role="gridcell"].AttendanceTimeCardsLayout-module__dateColumn___Wesi0')
            self._click_elemento(celda_fecha, f"celda fecha {info['label']}")
        except Exception:
            self._click_elemento(fila, f"fila {info['label']}")

        # Fallback para UIs que requieren foco + Enter para expandir.
        if (fila.get_attribute("aria-expanded") or "false") != "true":
            try:
                fila.send_keys(Keys.ENTER)
            except Exception:
                pass

        if (fila.get_attribute("aria-expanded") or "false") != "true":
            try:
                self.driver.execute_script("arguments[0].click();", fila)
            except Exception:
                pass

        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: (fila.get_attribute("aria-expanded") or "false") == "true"
            )
        except Exception:
            self.logger.warning(
                f"No se pudo expandir la fila de {info['label']}; se omite este dia para continuar."
            )
            return False

        aria_controls = fila.get_attribute("aria-controls")
        time.sleep(0.4)

        form = self._form(aria_controls)

        try:
            if nombre == "vie":
                self._rellenar_time_group(form, "periods.0.start", horario[0]["inicio"])
                self._rellenar_time_group(form, "periods.0.end", horario[0]["fin"])
                try:
                    btn_del = form.find_element(By.CSS_SELECTOR, 'button[data-test-id="timecard-delete-period-1"]')
                    btn_del.click()
                    time.sleep(0.4)
                    form = self._form(aria_controls)
                except Exception:
                    pass
            else:
                self._rellenar_time_group(form, "periods.0.start", horario[0]["inicio"])
                self._rellenar_time_group(form, "periods.0.end", horario[0]["fin"])
                self._rellenar_time_group(form, "periods.1.start", horario[1]["inicio"])
                self._rellenar_time_group(form, "periods.1.end", horario[1]["fin"])

                btn_add = form.find_element(By.CSS_SELECTOR, 'button[data-test-id="timecard-add-work"]')
                self._click_elemento(btn_add, "boton anadir tramo")
                time.sleep(0.5)
                form = self._form(aria_controls)
                self._rellenar_time_group(form, "periods.2.start", horario[2]["inicio"])
                self._rellenar_time_group(form, "periods.2.end", horario[2]["fin"])

            btn_save = form.find_element(By.CSS_SELECTOR, 'button[data-test-id="timecard-save-button"]')
            self._click_elemento(btn_save, "boton guardar")
            time.sleep(1.3)
            self.logger.info(f"Guardado completado para {info['label']}")
            return True
        except Exception as exc:
            self.logger.warning(
                f"No se pudo editar/guardar {info['label']} ({nombre}). Motivo: {exc}"
            )
            return False

    def rellenar_semana(self, solo_fecha: date | None = None):
        if solo_fecha is not None:
            fila_objetivo = self._obtener_fila_por_fecha(solo_fecha)
            if fila_objetivo is None:
                self.logger.info(f"No se encontro fila para SOLO_FECHA={solo_fecha}")
                return
            filas = [fila_objetivo]
            self.logger.info(
                f"Filtrado por SOLO_FECHA={solo_fecha}: {len(filas)} fila objetivo"
            )
        else:
            filas = self._obtener_filas()
            self.logger.info(
                "Dias detectados: "
                + ", ".join([f"{f['label']}({f['nombre']})" for f in filas])
            )
        self.logger.info(f"Inicio de procesamiento: {len(filas)} filas candidatas")

        for idx, info in enumerate(filas, start=1):
            fecha_dia: date | None = info.get("fecha")
            fecha_txt = fecha_dia.isoformat() if fecha_dia is not None else "desconocida"
            fecha_html = info.get("fecha_html")
            self.logger.info(
                f"Progreso {idx}/{len(filas)}: revisando label='{info['label']}', fecha_visible={fecha_txt}, datetime_html={fecha_html}, dia={info['nombre']}"
            )
            if fecha_dia is not None and fecha_dia > date.today():
                self.logger.info(
                    f"Saltando label='{info['label']}', fecha_visible={fecha_dia}, datetime_html={fecha_html}: es una fecha futura"
                )
                continue
            if info["tiene_horas"]:
                motivo = info.get("motivo_relleno", "detector")
                self.logger.info(
                    f"Saltando label='{info['label']}', fecha_visible={fecha_txt}, datetime_html={fecha_html}: ya tiene horas registradas ({motivo})"
                )
                continue
            self.logger.info(
                f"Intentando rellenar label='{info['label']}', fecha_visible={fecha_txt}, datetime_html={fecha_html}"
            )
            self._rellenar_dia(info)
            self.logger.info(
                f"Fin de intento para label='{info['label']}', fecha_visible={fecha_txt}, datetime_html={fecha_html}"
            )
            time.sleep(0.8)
