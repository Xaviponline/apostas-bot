import unittest

from analisador_inteligente import AnalisadorInteligente
from estatisticas_espn import EstatisticasESPN


class EstatisticasFake(EstatisticasESPN):
    def __init__(self, partidas):
        super().__init__(session=None)
        self.partidas = partidas

    def carregar_historicos(self, jogos, data_ref=None):
        return {"por.1": self.partidas}


class PremiumTests(unittest.TestCase):
    def setUp(self):
        self.jogo = {
            "id": 999,
            "casa": "Casa Forte",
            "fora": "Fora Fraco",
            "casa_id": 1,
            "fora_id": 2,
            "liga": "Portuguese Primeira Liga",
            "horario": "20:15",
        }
        partidas = []
        ts = 2000000000
        # Casa Forte: seis jogos em casa com forte produção ofensiva.
        for i in range(6):
            partidas.append({
                "id": 10+i, "liga_codigo": "por.1", "timestamp": ts-i,
                "casa_id": 1, "fora_id": 100+i,
                "casa": "Casa Forte", "fora": f"Rival {i}",
                "golos_casa": 2 + (i % 2), "golos_fora": i % 2,
            })
        # Fora Fraco: seis jogos fora com defesa vulnerável.
        for i in range(6):
            partidas.append({
                "id": 30+i, "liga_codigo": "por.1", "timestamp": ts-20-i,
                "casa_id": 200+i, "fora_id": 2,
                "casa": f"Rival B {i}", "fora": "Fora Fraco",
                "golos_casa": 2 + (i % 2), "golos_fora": i % 2,
            })
        # Fundo da liga para obter médias estáveis.
        for i in range(20):
            partidas.append({
                "id": 100+i, "liga_codigo": "por.1", "timestamp": ts-50-i,
                "casa_id": 300+i*2, "fora_id": 301+i*2,
                "casa": f"L{i}A", "fora": f"L{i}B",
                "golos_casa": 1 + (i % 2), "golos_fora": i % 2,
            })
        partidas.sort(key=lambda x: x["timestamp"], reverse=True)
        self.stats = EstatisticasFake(partidas)
        self.partidas = partidas

    def test_resolve_liga_portuguesa(self):
        self.assertEqual(EstatisticasESPN.resolver_liga(self.jogo), "por.1")

    def test_poisson_probabilities_are_coherent(self):
        p = EstatisticasESPN._probabilidades(1.6, 1.1)
        self.assertAlmostEqual(p["Vitória Casa"] + p["Empate"] + p["Vitória Fora"], 1.0, places=5)
        self.assertGreater(p["Over 1.5 Golos"], p["Over 2.5 Golos"])
        self.assertGreater(p["Under 3.5 Golos"], p["Under 2.5 Golos"])

    def test_real_sample_generates_model_not_random(self):
        analise = self.stats.analisar_jogo(self.jogo, self.partidas)
        self.assertIsNotNone(analise)
        self.assertGreaterEqual(analise["qualidade"], 55)
        self.assertGreater(analise["lambda_casa"], analise["lambda_fora"])
        motor = AnalisadorInteligente(estatisticas=self.stats)
        selecoes = motor.gerar_todas_apostas([self.jogo])
        self.assertTrue(selecoes)
        self.assertGreaterEqual(selecoes[0]["odd_minima"], 1.50)
        texto = motor.gerar_relatorio([self.jogo])
        self.assertIn("ANÁLISE PREMIUM", texto)
        self.assertIn("Odd justa", texto)
        self.assertNotIn("random", texto.lower())


if __name__ == "__main__":
    unittest.main()
