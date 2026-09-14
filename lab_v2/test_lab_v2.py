import unittest

from lab_v2.avaliacao import brier_score, calibracao, log_loss, validar_sem_lookahead
from lab_v2.walkforward import executar_walk_forward


class LabV2Tests(unittest.TestCase):
    def test_metricas_probabilisticas(self):
        dados = [
            {"probabilidade": 0.8, "resultado": 1},
            {"probabilidade": 0.7, "resultado": 1},
            {"probabilidade": 0.6, "resultado": 0},
        ]
        self.assertAlmostEqual(brier_score(dados), (0.04 + 0.09 + 0.36) / 3)
        self.assertGreater(log_loss(dados), 0)
        self.assertTrue(calibracao(dados))

    def test_lookahead_rejeitado(self):
        with self.assertRaises(ValueError):
            validar_sem_lookahead([
                {"timestamp_previsao": 100, "timestamp_jogo": 100}
            ])
        self.assertTrue(validar_sem_lookahead([
            {"timestamp_previsao": 99, "timestamp_jogo": 100}
        ]))

    def test_walkforward_nao_ve_o_futuro(self):
        jogos = [
            {"id": i, "liga": "L", "timestamp": i, "resultado": i % 2}
            for i in range(1, 7)
        ]
        tamanhos = []

        def predictor(historico, jogo):
            tamanhos.append((jogo["id"], len(historico)))
            return [{"mercado": "teste", "probabilidade": 0.6}]

        def resolver(jogo, mercado):
            return jogo["resultado"]

        previsoes = executar_walk_forward(
            jogos, predictor, resolver, min_historico=3
        )
        self.assertEqual(tamanhos, [(4, 3), (5, 4), (6, 5)])
        self.assertEqual(len(previsoes), 3)
        self.assertEqual(previsoes[0]["historico_disponivel"], 3)


if __name__ == "__main__":
    unittest.main()
