"""Protecao de quota OddsPapi para recolhas automaticas; sem alterar o modelo."""
import unittest
from unittest.mock import Mock

import requests

from main_sofascore import BotPremiumReal


class OddsQuotaFake:
    configurada = True
    provider = "oddspapi"
    ultimo_diagnostico_eventos = ""

    def __init__(self, remaining=17, error=None):
        self.remaining = remaining
        self.error = error

    def status_conta(self):
        if self.error:
            raise self.error
        return {"remaining": self.remaining, "request_count": 250 - (self.remaining or 0), "request_limit": 250}


class ReservaQuotaTests(unittest.TestCase):
    def _bot(self, remaining=17, error=None):
        return BotPremiumReal(
            token="teste", gestor=object(), owner_id=1, chat_id=1,
            buscador=object(), odds=OddsQuotaFake(remaining, error),
            analisador=object(), previsoes=object(),
        )

    def test_recolha_normal_bloqueia_com_17_pedidos(self):
        bot = self._bot(17)
        bot._capturar_odds_pendentes = Mock(return_value=1)
        self.assertEqual(bot._capturar_odds_se_devida(), 0)
        bot._capturar_odds_pendentes.assert_not_called()

    def test_recolha_normal_bloqueia_no_limiar_25(self):
        bot = self._bot(25)
        bot._capturar_odds_pendentes = Mock(return_value=1)
        self.assertEqual(bot._capturar_odds_se_devida(), 0)
        bot._capturar_odds_pendentes.assert_not_called()

    def test_recolha_normal_continua_acima_de_25(self):
        bot = self._bot(40)
        bot._capturar_odds_pendentes = Mock(return_value=2)
        self.assertEqual(bot._capturar_odds_se_devida(), 2)
        bot._capturar_odds_pendentes.assert_called_once_with()

    def test_clv_oficial_continua_com_17_pedidos(self):
        bot = self._bot(17)
        bot._selecoes_clv_proximas = Mock(return_value=[{"jogo": {"id": 1}}])
        bot._capturar_clv_pendentes = Mock(return_value=1)
        self.assertEqual(bot._capturar_clv_se_devido(), 1)
        bot._capturar_clv_pendentes.assert_called_once()

    def test_clv_oficial_para_a_zero(self):
        bot = self._bot(0)
        bot._selecoes_clv_proximas = Mock(return_value=[{"jogo": {"id": 1}}])
        bot._capturar_clv_pendentes = Mock(return_value=1)
        self.assertEqual(bot._capturar_clv_se_devido(), 0)
        bot._capturar_clv_pendentes.assert_not_called()

    def test_clv_tardio_nao_gasta_ultimos_10(self):
        bot = self._bot(10)
        bot._selecoes_clv_proximas = Mock(return_value=[{"jogo": {"id": 1}}])
        self.assertEqual(bot._capturar_clv_tardio_se_devido(), 0)

    def test_falha_da_conta_suspende_automaticos_sem_impedir_o_bot(self):
        bot = self._bot(error=requests.Timeout("conta indisponivel"))
        bot._capturar_odds_pendentes = Mock(return_value=1)
        bot._selecoes_clv_proximas = Mock(return_value=[{"jogo": {"id": 1}}])
        bot._capturar_clv_pendentes = Mock(return_value=1)
        self.assertEqual(bot._capturar_odds_se_devida(), 0)
        self.assertEqual(bot._capturar_clv_se_devido(), 0)
        bot._capturar_odds_pendentes.assert_not_called()
        bot._capturar_clv_pendentes.assert_not_called()

    def test_quota_desconhecida_suspende_odds_papi(self):
        bot = self._bot(remaining=None)
        bot._capturar_odds_pendentes = Mock(return_value=1)
        self.assertEqual(bot._capturar_odds_se_devida(), 0)
        bot._capturar_odds_pendentes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
