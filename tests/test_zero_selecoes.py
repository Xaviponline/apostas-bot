import unittest

from main_diario import BotPremiumDiario


class ZeroSelecoesTests(unittest.TestCase):
    def test_diagnostico_zero_mostra_contagens_sem_alterar_modelo(self):
        texto = BotPremiumDiario._diagnostico_zero(
            total_jogos=40,
            total_futuros=32,
            total_suportados=10,
            resumo_novo={"jogos": 32, "com_dados": 6, "selecoes": 0},
            selecoes_novas=[],
            erros_historico=1,
        )
        self.assertIn("Jogos encontrados hoje: 40", texto)
        self.assertIn("Futuros avaliados: 32", texto)
        self.assertIn("Dentro da cobertura V1: 10", texto)
        self.assertIn("Fora da cobertura: 22", texto)
        self.assertIn("Com dados suficientes: 6", texto)
        self.assertIn("Sem amostra suficiente: 4", texto)
        self.assertIn("Sem seleção após filtros: 6", texto)
        self.assertIn("Histórico indisponível em 1 competição", texto)


if __name__ == "__main__":
    unittest.main()
