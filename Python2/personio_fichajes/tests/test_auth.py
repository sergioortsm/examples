import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from personio_fichajes.src.auth import AuthManager
from personio_fichajes.src.config import Configuracion


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def debug(self, message):
        self.messages.append(("debug", message))


class FakeElement:
    def __init__(self, text="", tag_name="button", attributes=None, displayed=True, enabled=True):
        self.text = text
        self.tag_name = tag_name
        self.attributes = attributes or {}
        self.displayed = displayed
        self.enabled = enabled
        self.clicks = 0

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled

    def get_attribute(self, name):
        return self.attributes.get(name)

    def click(self):
        self.clicks += 1


class FakeDriver:
    def __init__(self, mapping, current_url="https://login.personio.com/"):
        self.mapping = mapping
        self.current_url = current_url

    def find_elements(self, by, value):
        return list(self.mapping.get(value, []))


class AuthManagerTests(unittest.TestCase):
    def setUp(self):
        cfg = Configuracion(employee_id=12345)
        self.logger = FakeLogger()
        self.auth = AuthManager(cfg, self.logger)

    def test_selecciona_boton_oidc_prioritario(self):
        oidc_button = FakeElement(
            text="Continuar con usuario Unikal",
            attributes={"type": "submit", "data-provider": "oidc"},
        )
        generic_button = FakeElement(text="Continuar")
        driver = FakeDriver(
            {
                "form[data-provider='oidc'] button[type='submit'][data-provider='oidc']": [oidc_button],
                "button, a[role='button'], input[type='submit'], a": [generic_button],
            }
        )

        candidato = self.auth._seleccionar_candidato_login_personio(driver)

        self.assertIsNotNone(candidato)
        self.assertIs(candidato["element"], oidc_button)
        self.assertIn("provider=oidc", candidato["description"])

    def test_descarta_cta_ambiguo_solo_con_continuar(self):
        ambiguous_button = FakeElement(text="Continuar")
        driver = FakeDriver(
            {
                "button, a[role='button'], input[type='submit'], a": [ambiguous_button],
            }
        )

        candidato = self.auth._seleccionar_candidato_login_personio(driver)

        self.assertIsNone(candidato)

    def test_no_repite_click_en_misma_pantalla_sin_transicion(self):
        oidc_button = FakeElement(
            text="Continuar con usuario Unikal",
            attributes={"type": "submit", "data-provider": "oidc"},
        )
        driver = FakeDriver(
            {
                "form[data-provider='oidc'] button[type='submit'][data-provider='oidc']": [oidc_button],
            }
        )
        estado = {"signature": None, "url": None, "retries": 0}

        self.auth._esperar_transicion_login_personio = lambda *args, **kwargs: False

        primer_resultado = self.auth._intentar_click_login_personio(
            driver, driver.current_url, estado
        )
        segundo_resultado = self.auth._intentar_click_login_personio(
            driver, driver.current_url, estado
        )

        self.assertEqual(primer_resultado, "stalled")
        self.assertEqual(segundo_resultado, "blocked")
        self.assertEqual(oidc_button.clicks, 1)
        self.assertEqual(estado["retries"], 2)

    def test_confirma_avance_si_cambia_la_url(self):
        clicked = FakeElement(text="Continuar con usuario Unikal")
        driver = SimpleNamespace(
            current_url="https://login.microsoftonline.com/common/oauth2",
            find_elements=lambda *args, **kwargs: [],
        )

        self.assertTrue(
            self.auth._ha_transicionado_login_personio(
                driver, "https://login.personio.com/", clicked
            )
        )


if __name__ == "__main__":
    unittest.main()