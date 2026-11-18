"""Regressao do mapeamento explicito sem pedidos HTTP."""
import unittest
from scout_shadow import _liga

class LigaBrasileiraTests(unittest.TestCase):
    def test_nome_do_relatorio(self):
        self.assertEqual(_liga({"liga": "Brasileiro Serie A"}), "soccer_brazil_campeonato")

    def test_mapeamento_italiano_existente_preservado(self):
        self.assertEqual(_liga({"liga": "Serie A"}), "soccer_italy_serie_a")

if __name__ == "__main__":
    unittest.main()
