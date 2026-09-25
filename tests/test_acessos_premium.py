import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from acessos_premium import GestorAcessosPremium
from main_competicoes import BotPremiumDiarioCompeticoes
from main_diario import TZ_PORTUGAL
from main_sofascore import AJUDA


class AcessosPremiumTests(unittest.TestCase):
    def test_adiciona_renova_expira_e_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            gestor = GestorAcessosPremium(Path(tmp) / "acessos.json")
            agora = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)

            primeiro = gestor.adicionar(123456, 30, agora=agora)
            estado = gestor.estado(123456, agora=agora)
            self.assertTrue(estado["ativo"])
            self.assertEqual(estado["user_id"], 123456)

            segundo = gestor.adicionar(
                123456, 5, agora=agora + timedelta(days=1)
            )
            validade1 = datetime.fromisoformat(
                primeiro["validade_ate"].replace("Z", "+00:00")
            )
            validade2 = datetime.fromisoformat(
                segundo["validade_ate"].replace("Z", "+00:00")
            )
            self.assertEqual(validade2 - validade1, timedelta(days=5))

            expirado = gestor.estado(
                123456, agora=validade2 + timedelta(seconds=1)
            )
            self.assertFalse(expirado["ativo"])

            self.assertTrue(gestor.remover(123456, agora=agora))
            self.assertFalse(gestor.estado(123456, agora=agora)["ativo"])

    def test_validacao_de_dias_e_user_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            gestor = GestorAcessosPremium(Path(tmp) / "acessos.json")
            with self.assertRaises(ValueError):
                gestor.adicionar(0, 30)
            with self.assertRaises(ValueError):
                gestor.adicionar(123, 0)
            with self.assertRaises(ValueError):
                gestor.adicionar(123, 3651)


class PremiumPicksTests(unittest.TestCase):
    def _bot(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = 999
        bot.chat_id = -100
        bot.username = "TesteBot"
        agora = datetime.now(TZ_PORTUGAL)
        futuro = (agora + timedelta(hours=2)).timestamp()
        passado = (agora - timedelta(minutes=5)).timestamp()
        bot.previsoes = type("Previsoes", (), {})()
        bot.previsoes.dados = {
            "previsoes": [
                {
                    "data_jogo": agora.strftime("%Y-%m-%d"),
                    "estado": "pendente",
                    "timestamp_jogo": futuro,
                    "casa": "Equipa A",
                    "fora": "Equipa B",
                    "mercado": "Ambas Marcam",
                    "probabilidade": 0.692,
                    "odd_minima": 1.52,
                    "ranking_modelo": 2,
                    "confianca_modelo": "ALTA",
                },
                {
                    "data_jogo": agora.strftime("%Y-%m-%d"),
                    "estado": "pendente",
                    "timestamp_jogo": passado,
                    "casa": "Jogo",
                    "fora": "Começado",
                    "mercado": "Over 2.5 Golos",
                    "probabilidade": 0.61,
                    "odd_minima": 1.70,
                    "ranking_modelo": 9,
                    "confianca_modelo": "MÉDIA",
                },
            ]
        }
        return bot

    def test_picks_cliente_so_mostra_snapshots_futuros_e_e_read_only(self):
        bot = self._bot()
        antes = copy.deepcopy(bot.previsoes.dados)

        texto = bot._executar_picks_cliente()

        self.assertIn("PREMIUM PICKS", texto)
        self.assertIn("Equipa A vs Equipa B", texto)
        self.assertIn("69,2%", texto)
        self.assertIn("Odd mínima ≥ 1,52", texto)
        self.assertIn("Ranking #2", texto)
        self.assertNotIn("Começado", texto)
        self.assertEqual(bot.previsoes.dados, antes)

    def test_cliente_so_e_aceite_em_chat_privado(self):
        bot = self._bot()

        class AcessosFake:
            def estado(self, user_id):
                return {"ativo": int(user_id) == 123}

        bot.acessos = AcessosFake()
        self.assertTrue(bot._cliente_ativo(123, 123))
        self.assertFalse(bot._cliente_ativo(-100777, 123))
        self.assertFalse(bot._cliente_ativo(124, 124))
        self.assertTrue(bot._cliente_ativo(-100777, 999))

    def test_comandos_admin_exigem_owner_e_chat_configurado(self):
        bot = self._bot()
        self.assertTrue(bot._e_owner_admin(-100, 999))
        self.assertFalse(bot._e_owner_admin(-101, 999))
        self.assertFalse(bot._e_owner_admin(-100, 998))


    def test_start_em_grupo_nao_expoe_id(self):
        bot = self._bot()

        class AcessosFake:
            def estado(self, user_id):
                return {"ativo": False}

        mensagens = []
        bot.acessos = AcessosFake()
        bot.enviar_mensagem = lambda chat_id, texto: mensagens.append((chat_id, texto))

        bot.processar_comando(-100777, "/start", user_id=123)

        self.assertEqual(len(mensagens), 1)
        self.assertIn("conversa privada", mensagens[0][1])
        self.assertNotIn("123", mensagens[0][1])

    def test_ajuda_admin_documenta_comandos_comerciais(self):
        self.assertIn("/clientes", AJUDA)
        self.assertIn("/cliente_add USER_ID DIAS", AJUDA)
        self.assertIn("/cliente_del USER_ID", AJUDA)
        self.assertIn("/picks", AJUDA)
        self.assertIn("/plano", AJUDA)


if __name__ == "__main__":
    unittest.main()
