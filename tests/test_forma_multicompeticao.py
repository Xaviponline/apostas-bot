import unittest

from main_enriquecido import EstatisticasESPNEnriquecidas


class FormaMulticompeticaoTests(unittest.TestCase):
    @staticmethod
    def _partida(ident, casa, fora, gc=2, gf=1, ts=1000):
        return {
            "id": ident,
            "liga_codigo": "teste",
            "timestamp": float(ts),
            "casa_id": casa,
            "fora_id": fora,
            "casa": f"T{casa}",
            "fora": f"T{fora}",
            "golos_casa": gc,
            "golos_fora": gf,
        }

    def _forma_equipa(self, team_id, inicio_id):
        jogos = []
        for i in range(8):
            adversario = 1000 + inicio_id + i
            if i % 2 == 0:
                jogos.append(self._partida(inicio_id + i, team_id, adversario, 2, 1, 8000 - i))
            else:
                jogos.append(self._partida(inicio_id + i, adversario, team_id, 1, 2, 8000 - i))
        return jogos

    def _baseline_taca(self):
        return [
            self._partida(200 + i, 2000 + i, 3000 + i, 2 if i % 2 == 0 else 1, 1, 6000 - i)
            for i in range(20)
        ]

    def test_taca_usa_forma_multicompeticao_sem_baixar_amostra_da_prova(self):
        stats = EstatisticasESPNEnriquecidas()
        stats._formas_globais = {
            1: self._forma_equipa(1, 10),
            2: self._forma_equipa(2, 30),
        }
        jogo = {
            "id": 999,
            "casa_id": 1,
            "fora_id": 2,
            "casa": "Casa",
            "fora": "Fora",
            "liga": "English Carabao Cup",
            "league_code": "eng.league_cup",
        }

        analise = stats.analisar_jogo(jogo, self._baseline_taca())
        self.assertIsNotNone(analise)
        self.assertEqual(analise["forma_fonte"], "multicompeticao")
        self.assertEqual(analise["amostra_casa"], 8)
        self.assertEqual(analise["amostra_fora"], 8)
        self.assertEqual(analise["amostra_liga"], 20)

    def test_taca_continua_a_exigir_base_minima_da_competicao(self):
        stats = EstatisticasESPNEnriquecidas()
        stats._formas_globais = {
            1: self._forma_equipa(1, 10),
            2: self._forma_equipa(2, 30),
        }
        jogo = {
            "casa_id": 1,
            "fora_id": 2,
            "liga": "English Carabao Cup",
            "league_code": "eng.league_cup",
        }
        self.assertIsNone(stats.analisar_jogo(jogo, self._baseline_taca()[:9]))

    def test_liga_normal_nao_depende_da_forma_global(self):
        stats = EstatisticasESPNEnriquecidas()
        stats._formas_globais = {}
        partidas = self._baseline_taca()
        partidas.extend(self._forma_equipa(1, 50))
        partidas.extend(self._forma_equipa(2, 70))
        partidas.sort(key=lambda x: x["timestamp"], reverse=True)
        jogo = {
            "casa_id": 1,
            "fora_id": 2,
            "liga": "Spanish LaLiga",
            "league_code": "esp.1",
        }
        analise = stats.analisar_jogo(jogo, partidas)
        self.assertIsNotNone(analise)
        self.assertNotIn("forma_fonte", analise)

    def test_precarga_so_para_tacas_e_uefa(self):
        class Probe(EstatisticasESPNEnriquecidas):
            def __init__(self):
                super().__init__()
                self.pedidos_forma = []

            def _fetch_liga(self, liga_codigo, data_ref=None):
                return []

            def _fetch_forma_global(self, team_id, data_ref=None):
                self.pedidos_forma.append(team_id)
                return []

        stats = Probe()
        jogos = [
            {"league_code": "eng.league_cup", "casa_id": 1, "fora_id": 2},
            {"league_code": "esp.1", "casa_id": 3, "fora_id": 4},
            {"league_code": "uefa.europa", "casa_id": 5, "fora_id": 6},
            {"league_code": "uefa.nations", "casa_id": 7, "fora_id": 8},
        ]
        stats.carregar_historicos(jogos)
        self.assertEqual(set(stats.pedidos_forma), {1, 2, 5, 6, 7, 8})

    def test_amigavel_nao_entra_na_forma_global(self):
        evento = {
            "name": "Club Friendly",
            "season": {"slug": "club-friendly"},
            "competitions": [],
        }
        self.assertFalse(EstatisticasESPNEnriquecidas._evento_oficial(evento))
        self.assertTrue(
            EstatisticasESPNEnriquecidas._evento_oficial(
                {"name": "League Match", "season": {"slug": "english-premier-league"}}
            )
        )


if __name__ == "__main__":
    unittest.main()
