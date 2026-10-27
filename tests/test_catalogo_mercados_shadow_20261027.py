import unittest
from catalogo_mercados_shadow import analisar_catalogo

class TestCatalogo(unittest.TestCase):
    def test_missing_market(self):
        result = analisar_catalogo({}, {'mercados': [{'id': '206'}]})
        self.assertEqual(result['motivos']['id_ausente_no_catalogo'], 1)

    def test_valid_market(self):
        catalog = {'206': {'name': 'Over Under Full Time', 'period': 'fulltime', 'outcomes': {'207': 'Under'}}}
        odds = {'mercados': [{'id': '206', 'odds': [{'seleção': 'Under'}]}]}
        self.assertEqual(analisar_catalogo(catalog, odds)['motivos'], {})

if __name__ == '__main__':
    unittest.main()
