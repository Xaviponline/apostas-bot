import unittest
from time_machine_auditoria_shadow import auditar


class AuditoriaTimeMachineTests(unittest.TestCase):
    def test_contagens(self):
        rows = [
            dict(resultado_binario=1, odd_real=1.8, odd_minima=1.7, odd_fecho=1.6, data_jogo="2026-10-20", mercado="Under 2.5"),
            dict(resultado_binario=0, odd_real=None, odd_minima=1.7, data_jogo="2026-10-21", mercado="Under 2.5"),
            dict(resultado_binario=None, odd_real=2.1, odd_minima=1.7),
        ]
        result = auditar(rows)
        self.assertEqual(result["registos"], 3)
        self.assertEqual(result["liquidados"], 2)
        self.assertEqual(result["com_odd_real"], 1)
        self.assertEqual(result["elegiveis_odd_minima"], 1)
        self.assertNotIn("roi", result)

    def test_formato_invalido(self):
        with self.assertRaises(ValueError):
            auditar({})


if __name__ == "__main__":
    unittest.main()
