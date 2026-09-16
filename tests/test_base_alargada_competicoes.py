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
                self.intervalos = []

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.intervalos.append((liga_codigo, inicio, fim))
                return []

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        stats._fetch_liga("eng.league_cup", ref)
        codigo, inicio, fim = stats.intervalos[0]
        self.assertEqual(codigo, "eng.league_cup")
        self.assertGreaterEqual((fim - inicio).days, 400)
        self.assertTrue(
            any((fim_bloco - inicio_bloco).days <= 59 for _, inicio_bloco, fim_bloco in stats.intervalos[1:])
        )

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

            def _recolher_por_dias(self, liga_codigo, inicio, fim):
                raise AssertionError("fallback diário não deve ser usado")

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        with self.assertRaises(requests.Timeout):
            stats._fetch_liga("uefa.europa", ref)

    def test_bloco_isolado_pode_falhar_se_houver_amostra_minima(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__()
                self.chamadas = 0

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.chamadas += 1
                if self.chamadas in (1, 2):
                    raise requests.Timeout("falha transitória")
                return [
                    {"id": 100 + i, "timestamp": float(1000 - i)}
                    for i in range(12)
                ]

            def _normalizar_eventos(self, eventos, liga_codigo):
                return {evento["id"]: dict(evento) for evento in eventos}

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        historico = stats._fetch_liga("eng.league_cup", ref)
        self.assertGreaterEqual(len(historico), stats.MIN_JOGOS_BASE)

    def test_resposta_longa_vazia_tenta_blocos_menores(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__()
                self.chamadas = 0

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.chamadas += 1
                if self.chamadas == 1:
                    return []
                return [
                    {"id": 200 + i, "timestamp": float(2000 - i)}
                    for i in range(10)
                ]

            def _normalizar_eventos(self, eventos, liga_codigo):
                return {evento["id"]: dict(evento) for evento in eventos}

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        historico = stats._fetch_liga("uefa.europa", ref)
        self.assertEqual(len(historico), 10)
        self.assertGreaterEqual(stats.chamadas, 2)


if __name__ == "__main__":
    unittest.main()
