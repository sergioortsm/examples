import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from personio_fichajes.src import editor_config


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def build_app(ruta_config: Path):
    app = editor_config.EditorConfigApp.__new__(editor_config.EditorConfigApp)
    app.ruta_config = ruta_config
    app.vars = {
        "employee_id": DummyVar("12345"),
        "timezone": DummyVar("Europe/Madrid"),
        "base_url": DummyVar("https://unikaltech.app.personio.com"),
        "morning_start": DummyVar("08:30"),
        "morning_end": DummyVar("14:30"),
        "afternoon_start": DummyVar("15:30"),
        "afternoon_end": DummyVar("18:00"),
        "friday_start": DummyVar("09:00"),
        "friday_end": DummyVar("15:00"),
        "headless": DummyVar(True),
        "modo_prueba": DummyVar(False),
        "modo_interactivo": DummyVar(True),
    }
    return app


class EditorConfigAppTests(unittest.TestCase):
    def test_crear_payload_convierte_y_valida_campos_minimos(self):
        ruta = Path(tempfile.gettempdir()) / "config_test_payload.json"
        app = build_app(ruta)

        payload = app._crear_payload()

        self.assertEqual(payload["employee_id"], 12345)
        self.assertIsInstance(payload["employee_id"], int)
        self.assertTrue(payload["headless"])
        self.assertFalse(payload["modo_prueba"])
        self.assertTrue(payload["modo_interactivo"])

    def test_crear_payload_falla_con_employee_id_invalido(self):
        ruta = Path(tempfile.gettempdir()) / "config_test_invalid.json"
        app = build_app(ruta)
        app.vars["employee_id"].set("abc")

        with self.assertRaisesRegex(ValueError, "employee_id debe ser un numero entero"):
            app._crear_payload()

    def test_guardar_persist_json_minimo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ruta = Path(temp_dir) / "configuracion.json"
            app = build_app(ruta)

            with patch.object(editor_config.messagebox, "showinfo") as showinfo:
                app.guardar()

            self.assertTrue(ruta.exists())
            with ruta.open("r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)

            self.assertEqual(data["employee_id"], 12345)
            self.assertEqual(data["timezone"], "Europe/Madrid")
            self.assertEqual(data["base_url"], "https://unikaltech.app.personio.com")
            showinfo.assert_called_once()

    def test_cargar_json_invalido_devuelve_dict_vacio_y_avisa(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ruta = Path(temp_dir) / "configuracion.json"
            ruta.write_text("{ invalido", encoding="utf-8")

            app = editor_config.EditorConfigApp.__new__(editor_config.EditorConfigApp)
            app.ruta_config = ruta

            with patch.object(editor_config.messagebox, "showwarning") as showwarning:
                data = app._cargar()

            self.assertEqual(data, {})
            showwarning.assert_called_once()


if __name__ == "__main__":
    unittest.main()