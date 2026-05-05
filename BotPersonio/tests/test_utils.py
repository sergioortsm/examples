import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils import aplicar_desfase_horario, hora_a_minutos, parse_hhmm


class FakeLogger:
    def info(self, message):
        pass


class UtilsDesfaseTests(unittest.TestCase):
    def test_descanso_siempre_exactamente_60_minutos_en_dos_tramos(self):
        cfg = SimpleNamespace(employee_id=123, desfase_horario_max_min=10)
        logger = FakeLogger()
        horario = [
            {"tipo": "trabajo", "inicio": parse_hhmm("08:30"), "fin": parse_hhmm("14:30")},
            {"tipo": "descanso", "inicio": parse_hhmm("14:30"), "fin": parse_hhmm("15:30")},
            {"tipo": "trabajo", "inicio": parse_hhmm("15:30"), "fin": parse_hhmm("18:00")},
        ]

        resultado = aplicar_desfase_horario(cfg, logger, horario, "lun", date(2026, 5, 4))

        fin_manana = hora_a_minutos(resultado[0]["fin"])
        inicio_tarde = hora_a_minutos(resultado[2]["inicio"])
        self.assertEqual(inicio_tarde - fin_manana, 60)


if __name__ == "__main__":
    unittest.main()
