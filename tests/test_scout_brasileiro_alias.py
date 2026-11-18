"""Regressao do mapeamento explicito sem pedidos HTTP."""
import unittest
from scout_shadow import _liga

class LigaBrasileiraTests(unittest.TestCase):
    def test_nome_do_relatorio(self):
        self.assertEqual(_liga({"liga": "Brasileiro Serie A"}), "soccer_brazil_campeonato")

    def test_nome_ambiguo_nao_e_aceite(self):
        self.assertIsNone(_liga({"liga": "Serie A"}))

if __name__ == "__main__":
    unittest.main()
