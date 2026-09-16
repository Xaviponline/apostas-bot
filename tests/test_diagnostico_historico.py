import unittest
from types import SimpleNamespace

import requests

from estatisticas_espn_resiliente import EstatisticasESPNResiliente
from main_enriquecido import BotPremiumDiarioDiagnostico


class DiagnosticoHistoricoTests(unittest.TestCase):
    def test_http_status_e_resumido_sem_expor_payload(self):
        resposta = requests.Response()
        resposta.status_code = 403
        erro = requests.HTTPError("segredo-nao-deve-aparecer", response=resposta)
        self.assertEqual(EstatisticasESPNResiliente._motivo_seguro(erro), "HTTP 403")

    def test_diagnostico_zero_mostra_motivo_por_codigo(self):
        bot = BotPremiumDiarioDiagnostico.__new__(BotPremiumDiarioDiagnostico)
        bot.analisador = SimpleNamespace(
            estatisticas=SimpleNamespace(ultimo_erros={"esp.1": "HTTP 403"})
        )
        texto = bot._diagnostico_zero(
            total_jogos=10,
            total_futuros=10,
            total_suportados=2,
            resumo_novo={"com_dados": 0},
            selecoes_novas=[],
            fora_cobertura=[("Outra Liga", 8)],
            historico_indisponivel=["Spanish LaLiga [esp.1]"],
            jogos_historico_indisponivel=2,
        )
        self.assertIn("Motivo técnico: esp.1: HTTP 403", texto)
        self.assertNotIn("segredo-nao-deve-aparecer", texto)


if __name__ == "__main__":
    unittest.main()
