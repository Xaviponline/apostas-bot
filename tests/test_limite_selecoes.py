import unittest

from analisador_inteligente import AnalisadorInteligente


class EstatisticasTudoValido:
    ultimo_erros = {}

    @staticmethod
    def resolver_liga(jogo):
        return "por.1"

    def carregar_historicos(self, jogos, data_ref=None):
        return {"por.1": []}

    def analisar_jogo(self, jogo, partidas):
        return {
            "jogo": jogo,
            "qualidade": 90,
            "probabilidades": {"Over 2.5 Golos": 0.70},
        }




class EstatisticasRankingV12(EstatisticasTudoValido):
    def analisar_jogo(self, jogo, partidas):
        if jogo["id"] == 1:
            return {
                "jogo": jogo,
                "qualidade": 100,
                "probabilidades": {"Over 2.5 Golos": 0.66},
            }
        return {
            "jogo": jogo,
            "qualidade": 55,
            "probabilidades": {"Over 2.5 Golos": 0.70},
        }


class LimiteSelecoesTests(unittest.TestCase):
    def test_maximo_de_20_selecoes_por_analise(self):
        jogos = [
            {
                "id": i,
                "casa": f"Casa {i}",
                "fora": f"Fora {i}",
                "liga": "Portuguese Primeira Liga",
            }
            for i in range(25)
        ]
        motor = AnalisadorInteligente(estatisticas=EstatisticasTudoValido())
        selecoes = motor.gerar_todas_apostas(jogos)

        self.assertEqual(AnalisadorInteligente.MAX_SELECOES, 20)
        self.assertEqual(len(selecoes), 20)
        self.assertEqual(motor.ultimo_resumo["selecoes"], 20)
        self.assertEqual([s["ranking_modelo"] for s in selecoes], list(range(1, 21)))

    def test_v12_ranking_nao_promove_qualidade_em_detrimento_da_probabilidade(self):
        jogos = [
            {"id": 1, "casa": "Alta Q", "fora": "Fora", "liga": "Portuguese Primeira Liga"},
            {"id": 2, "casa": "Baixa Q", "fora": "Fora", "liga": "Portuguese Primeira Liga"},
        ]
        motor = AnalisadorInteligente(estatisticas=EstatisticasRankingV12())
        selecoes = motor.gerar_todas_apostas(jogos)

        self.assertEqual(len(selecoes), 2)
        self.assertEqual(selecoes[0]["jogo"]["id"], 2)
        self.assertEqual(selecoes[0]["ranking_modelo"], 1)
        self.assertEqual(selecoes[1]["jogo"]["id"], 1)
        self.assertEqual(selecoes[1]["ranking_modelo"], 2)


if __name__ == "__main__":
    unittest.main()
