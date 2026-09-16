import unittest

from main_diario import BotPremiumDiario


class ZeroSelecoesTests(unittest.TestCase):
    def test_diagnostico_zero_mostra_contagens_e_competicoes_sem_alterar_modelo(self):
        texto = BotPremiumDiario._diagnostico_zero(
            total_jogos=40,
            total_futuros=32,
            total_suportados=10,
            resumo_novo={"jogos": 32, "com_dados": 6, "selecoes": 0},
            selecoes_novas=[],
            fora_cobertura=[("Regular Season", 12), ("Copa Exemplo", 10)],
            historico_indisponivel=["UEFA Europa League [uefa.europa]"],
            jogos_historico_indisponivel=2,
        )
        self.assertIn("Jogos encontrados hoje: 40", texto)
        self.assertIn("Futuros avaliados: 32", texto)
        self.assertIn("Dentro da cobertura V1: 10", texto)
        self.assertIn("Fora da cobertura: 22", texto)
        self.assertIn("Com dados suficientes: 6", texto)
        self.assertIn("Sem amostra suficiente: 2", texto)
        self.assertIn("Sem seleção após filtros: 6", texto)
        self.assertIn("Regular Season (12)", texto)
        self.assertIn("Copa Exemplo (10)", texto)
        self.assertIn("Histórico indisponível: UEFA Europa League [uefa.europa]", texto)

    def test_contagem_competicoes_ordena_por_quantidade(self):
        jogos = [
            {"liga": "Liga B"},
            {"liga": "Liga A"},
            {"liga": "Liga B"},
            {"liga": "Liga C"},
            {"liga": "Liga A"},
            {"liga": "Liga B"},
        ]
        self.assertEqual(
            BotPremiumDiario._contar_competicoes(jogos),
            [("Liga B", 3), ("Liga A", 2), ("Liga C", 1)],
        )


if __name__ == "__main__":
    unittest.main()
