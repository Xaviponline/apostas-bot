"""Códigos de falha da conta OddsPapi sem fugas de segredos e sem consultas pagas."""
import unittest
from unittest.mock import Mock

import requests

from main_competicoes import BotPremiumDiarioCompeticoes


class OddsStatusFalhasTests(unittest.TestCase):
    @staticmethod
    def _bot(erro):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.username = None
        bot.owner_id = bot.chat_id = 123
        bot.odds = Mock(configurada=True, nome_fonte="OddsPapi / Betano PT")
        bot.odds.status_conta = Mock(side_effect=erro)
        bot.enviar_mensagem = Mock()
        return bot

    @staticmethod
    def _erro_http(codigo):
        segredo = "SEGREDO-NAO-EXPOR"
        response = requests.Response()
        response.status_code = codigo
        response.url = "https://api.oddspapi.io/v4/account?apiKey=" + segredo
        erro = requests.HTTPError(response.url, response=response)
        return erro, segredo

    def test_erro_http_403_mostra_status_sem_chave_ou_url(self):
        erro, segredo = self._erro_http(403)
        bot = self._bot(erro)
        bot.processar_comando(123, "/odds_status", user_id=123)
        texto = bot.enviar_mensagem.call_args.args[1]
        self.assertIn("odds_http_403", texto)
        self.assertIn("Acesso proibido", texto)
        self.assertNotIn(segredo, texto)
        self.assertNotIn("https://", texto)
        bot.odds.status_conta.assert_called_once_with()

    def test_erro_http_401_e_502_informam_categorias_distintas(self):
        for codigo, esperado in ((401, "autenticacao"), (502, "Erro do servidor")):
            erro, segredo = self._erro_http(codigo)
            bot = self._bot(erro)
            bot.processar_comando(123, "/odds_status", user_id=123)
            texto = bot.enviar_mensagem.call_args.args[1]
            self.assertIn(f"odds_http_{codigo}", texto)
            self.assertIn(esperado, texto)
            self.assertNotIn(segredo, texto)

    def test_timeout_nao_revela_mensagem_de_erro_original(self):
        bot = self._bot(requests.Timeout("erro interno SEGREDO-NAO-EXPOR"))
        bot.processar_comando(123, "/odds_status", user_id=123)
        texto = bot.enviar_mensagem.call_args.args[1]
        self.assertIn("odds_timeout", texto)
        self.assertNotIn("SEGREDO-NAO-EXPOR", texto)

    def test_so_admin_pode_ver_diagnostico(self):
        erro, _ = self._erro_http(403)
        bot = self._bot(erro)
        bot.processar_comando(123, "/odds_status", user_id=999)
        bot.enviar_mensagem.assert_not_called()
        bot.odds.status_conta.assert_not_called()


if __name__ == "__main__":
    unittest.main()
