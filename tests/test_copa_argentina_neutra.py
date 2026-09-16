import unittest

from estatisticas_forma_web import EstatisticasFormaWeb


def resultado(event_id, team_id, opponent_id, gf, ga, local, ts):
    if local == "casa":
        return {
            "id": event_id,
            "liga_codigo": "all",
            "timestamp": ts,
            "casa_id": team_id,
            "fora_id": opponent_id,
            "casa": f"T{team_id}",
            "fora": f"T{opponent_id}",
            "golos_casa": gf,
            "golos_fora": ga,
        }
    return {
        "id": event_id,
        "liga_codigo": "all",
        "timestamp": ts,
        "casa_id": opponent_id,
        "fora_id": team_id,
        "casa": f"T{opponent_id}",
        "fora": f"T{team_id}",
        "golos_casa": ga,
        "golos_fora": gf,
    }


def forma_equipa(team_id, locais):
    saida = []
    for i, local in enumerate(locais):
        # Mantém a mesma produção/sofrimento independentemente do rótulo de local.
        gf = 2 if i % 2 == 0 else 1
        ga = 0 if i % 3 else 1
        saida.append(
            resultado(1000 + team_id * 100 + i, team_id, 9000 + i, gf, ga, local, 2000000000 - i)
        )
    return saida


class CopaArgentinaNeutraTests(unittest.TestCase):
    def _stats(self, locais_casa, locais_fora):
        stats = EstatisticasFormaWeb()
        stats._formas_globais = {
            1: forma_equipa(1, locais_casa),
            2: forma_equipa(2, locais_fora),
        }
        return stats

    @staticmethod
    def _base_copa():
        jogos = []
        for i in range(28):
            jogos.append(
                {
                    "id": 5000 + i,
                    "liga_codigo": "arg.copa",
                    "timestamp": 1900000000 - i,
                    "casa_id": 100 + i,
                    "fora_id": 200 + i,
                    "casa": f"C{i}",
                    "fora": f"F{i}",
                    "golos_casa": 2 if i % 2 == 0 else 1,
                    "golos_fora": 1 if i % 3 == 0 else 0,
                }
            )
        return jogos

    @staticmethod
    def _jogo():
        return {
            "id": 999,
            "league_code": "arg.copa",
            "liga": "Argentine Copa Argentina",
            "casa_id": 1,
            "fora_id": 2,
            "casa": "Independiente Rivadavia",
            "fora": "Atlético Tucumán",
        }

    def test_copa_argentina_ignora_rotulo_casa_fora_na_forma(self):
        base = self._base_copa()
        a = self._stats(["casa"] * 6 + ["fora"] * 2, ["fora"] * 6 + ["casa"] * 2)
        b = self._stats(["fora"] * 6 + ["casa"] * 2, ["casa"] * 6 + ["fora"] * 2)

        analise_a = a.analisar_jogo(self._jogo(), base)
        analise_b = b.analisar_jogo(self._jogo(), base)

        self.assertEqual(analise_a["contexto_partida"], "neutro")
        self.assertEqual(analise_a["amostra_casa"], 8)
        self.assertEqual(analise_a["amostra_fora"], 8)
        self.assertAlmostEqual(analise_a["lambda_casa"], analise_b["lambda_casa"], places=9)
        self.assertAlmostEqual(analise_a["lambda_fora"], analise_b["lambda_fora"], places=9)

    def test_base_neutra_e_metade_da_media_total_da_prova(self):
        base = self._base_copa()
        stats = self._stats(["casa", "fora"] * 4, ["fora", "casa"] * 4)
        analise = stats.analisar_jogo(self._jogo(), base)

        media_home = sum(x["golos_casa"] for x in base) / len(base)
        media_away = sum(x["golos_fora"] for x in base) / len(base)
        self.assertAlmostEqual(
            analise["baseline_neutro"], (media_home + media_away) / 2.0, places=9
        )
        self.assertEqual(analise["forma_fonte"], "multicompeticao")
        self.assertGreaterEqual(analise["qualidade"], 55)


if __name__ == "__main__":
    unittest.main()
