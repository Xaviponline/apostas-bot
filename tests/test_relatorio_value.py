import unittest

from analisador_inteligente import AnalisadorInteligente


class RelatorioValueTests(unittest.TestCase):
    @staticmethod
    def _selecao(nome, odd_real=None, odd_minima=1.60):
        selecao = {
            "jogo": {
                "casa": nome,
                "fora": "Adversário",
                "liga": "LaLiga",
                "horario": "20:00",
            },
            "mercado": "Under 3.5 Golos",
            "probabilidade": 0.65,
            "odd_justa": 1.54,
            "odd_minima": odd_minima,
            "confianca": "MÉDIA",
            "qualidade": 70,
        }
        if odd_real is not None:
            selecao["odd_real"] = odd_real
            selecao["ev_real"] = (0.65 * odd_real) - 1.0
        return selecao

    def test_relatorio_distingue_valor_sem_valor_e_sem_odd(self):
        analisador = AnalisadorInteligente(estatisticas=object())
        selecoes = [
            self._selecao("Com valor", odd_real=1.70),
            self._selecao("Sem valor", odd_real=1.30),
            self._selecao("Sem odd"),
        ]
        analisador.ultimo_resumo = {"jogos": 3, "com_dados": 3, "selecoes": 3}

        relatorio = analisador.gerar_relatorio([], selecoes=selecoes)

        self.assertIn("🟢 VALOR CONFIRMADO", relatorio)
        self.assertIn("🔴 SEM VALOR À ODD ATUAL", relatorio)
        self.assertIn("⚪ ODD REAL INDISPONÍVEL", relatorio)
        self.assertIn(
            "🧭 Validação de mercado: 1 com valor | 1 abaixo da mínima | 1 sem odd real.",
            relatorio,
        )


if __name__ == "__main__":
    unittest.main()
