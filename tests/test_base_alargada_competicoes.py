import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from estatisticas_espn_competicoes import EstatisticasESPNCompeticoes


class BaseAlargadaCompeticoesTests(unittest.TestCase):
    def test_taca_usa_blocos_de_14_dias(self):
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
        self.assertGreater(len(stats.intervalos), 1)
        self.assertTrue(
            all((fim - inicio).days <= 13 for _, inicio, fim in stats.intervalos)
        )
        self.assertEqual(stats.diagnostico_base["eng.league_cup"]["fonte"], "blocos_14d")

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
        diag = stats.diagnostico_base["uefa.europa"]
        self.assertGreater(diag["blocos_falha"], 0)
        self.assertIn("timeout", diag["motivos"])

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
        diag = stats.diagnostico_base["eng.league_cup"]
        self.assertGreaterEqual(diag["blocos_ok"], 1)

    def test_para_quando_atinge_alvo_de_jogos(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__()
                self.chamadas = 0

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.chamadas += 1
                base = 1000 * self.chamadas
                return [
                    {"id": base + i, "timestamp": float(base - i)}
                    for i in range(12)
                ]

            def _normalizar_eventos(self, eventos, liga_codigo):
                return {evento["id"]: dict(evento) for evento in eventos}

        stats = Probe()
        ref = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        historico = stats._fetch_liga("uefa.europa", ref)
        self.assertGreaterEqual(len(historico), stats.ALVO_JOGOS_BASE)
        self.assertLessEqual(stats.chamadas, 3)


    def test_nations_league_alcanca_ciclo_anterior(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__(dias_historico=70)
                self.intervalos = []

            def _consultar_intervalo(self, liga_codigo, inicio, fim):
                self.intervalos.append((liga_codigo, inicio, fim))
                return []

        stats = Probe()
        ref = datetime(2026, 9, 24, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        stats._fetch_liga("uefa.nations", ref)
        inicio_mais_antigo = min(inicio for _, inicio, _ in stats.intervalos)
        fim = ref.date()
        self.assertGreaterEqual((fim - inicio_mais_antigo).days, 890)
        self.assertEqual(stats.DIAS_BASE_POR_LIGA["uefa.nations"], 900)



if __name__ == "__main__":
    unittest.main()
