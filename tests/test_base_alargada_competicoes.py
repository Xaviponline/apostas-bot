import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from estatisticas_espn_competicoes import EstatisticasESPNCompeticoes


class BaseAlargadaCompeticoesTests(unittest.TestCase):
    def test_taca_usa_janela_alargada(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__(dias_historico=70)
                self.intervalo = None

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.intervalo = (liga_codigo, inicio, fim)
                return []

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        stats._fetch_liga("eng.league_cup", ref)
        codigo, inicio, fim = stats.intervalo
        self.assertEqual(codigo, "eng.league_cup")
        self.assertGreaterEqual((fim - inicio).days, 400)

    def test_liga_normal_mantem_janela_v1(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__(dias_historico=70)
                self.intervalo = None

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.intervalo = (liga_codigo, inicio, fim)
                return []

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        stats._fetch_liga("esp.1", ref)
        _, inicio, fim = stats.intervalo
        self.assertEqual((fim - inicio).days, 70)

    def test_taca_nao_faz_fallback_diario_de_420_dias(self):
        class Probe(EstatisticasESPNCompeticoes):
            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                raise requests.Timeout("teste")

            def _recolher_por_blocos(self, liga_codigo, inicio, fim):
                return {}

            def _recolher_por_dias(self, liga_codigo, inicio, fim):
                raise AssertionError("fallback diário não deve ser usado")

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        self.assertEqual(stats._fetch_liga("uefa.europa", ref), [])


if __name__ == "__main__":
    unittest.main()
