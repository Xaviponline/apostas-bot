"""Regressao: diagnostico agregado de mercados nao altera selecoes ou odds."""
import copy
import unittest
from unittest.mock import patch

from odds_auditoria import AuditoriaOdds


class FonteLocal:
    provider = "oddspapi"
    configurada = True

    def eventos_hoje(self):
        return [{"id": "17", "casa": "Casa", "fora": "Fora",
                 "data": "2026-11-06T19:00:00Z", "liga": "Teste"}]

    def odds_evento(self, event_id):
        return {"id": "17", "casa": "Casa", "fora": "Fora",
                "bookmaker_disponivel": True,
                "mercados": [{"name": "Full Time Goals Total",
                              "period": "fulltime", "handicap": 2.5,
                              "odds": [{"seleção": "Under", "odd": 1.85}]}]}


class OddsMercadosShadowTests(unittest.TestCase):
    def test_log_agregado_nao_cria_odd(self):
        selecoes = [{"jogo": {"casa": "Casa", "fora": "Fora",
                              "timestamp": 1793991600.0},
                     "mercado": "Under 2.5 Golos"}]
        antes = copy.deepcopy(selecoes)
        with patch("odds_auditoria.logging.info") as info:
            saida = AuditoriaOdds(FonteLocal()).enriquecer(selecoes)
        self.assertEqual(selecoes, antes)
        self.assertNotIn("odd_real", saida[0])
        self.assertEqual(saida[0]["_odds_diag"], "mercado_nao_disponivel")
        logs = [call for call in info.call_args_list
                if call.args and "ODDS_MERCADOS_SHADOW" in call.args[0]]
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].args[1:], ("mercado_nao_disponivel", 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
