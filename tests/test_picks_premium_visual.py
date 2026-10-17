"""Tests de apresentação Premium: apenas leitura e sem alterar VALUE."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes


TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 17, 11, 0, tzinfo=TZ)


class RelogioFixo:
    @staticmethod
    def now(tz=None):
        return AGORA.astimezone(tz) if tz else AGORA


def exemplo(rank, hora, estado="confirmado", odd=1.72, minima=1.50, data="2030-10-17"):
    return {
        "data_jogo": data,
        "timestamp_jogo": (AGORA + timedelta(hours=hora)).timestamp(),
        "estado": "pendente",
        "ranking_modelo": rank,
        "casa": f"Clube {rank}",
        "fora": f"Visitante {rank}",
        "mercado": "Under 2.5 Golos",
        "probabilidade": 0.66,
        "odd_minima": minima,
        "confianca_modelo": "ALTA",
        "valor_estado": estado,
        "odd_valor_confirmado": odd if estado == "confirmado" else None,
        "odd_real": odd if estado == "confirmado" else None,
        "odd_mercado_atual": odd if estado in ("sem_valor", "expirado") else None,
    }


class PicksPremiumVisualTests(unittest.TestCase):
    def _painel(self, picks):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = SimpleNamespace(dados={"previsoes": picks})
        antes = copy.deepcopy(bot.previsoes.dados)
        with patch("main_competicoes.datetime", RelogioFixo):
            painel = bot._executar_picks_cliente()
        self.assertEqual(bot.previsoes.dados, antes)
        return painel

    def test_separa_cinco_value_aguarda_sem_valor_sem_mutacao(self):
        picks = [
            exemplo(3, 2, estado="confirmado", odd=2.02, minima=1.51),
            exemplo(4, 3, estado="sem_odd", odd=None, minima=1.51),
            exemplo(12, 2, estado="sem_valor", odd=1.50, minima=1.53),
            exemplo(8, 4, estado="confirmado", odd=1.72, minima=1.52),
            exemplo(1, 4, estado="expirado", odd=1.31, minima=1.50),
        ]
        p = self._painel(picks)
        self.assertIn("📊 5 seleções ainda por começar", p)
        self.assertIn("🟢 2 com VALUE registado", p)
        self.assertIn("🟡 1 sem odd válida", p)
        self.assertIn("🔴 2 sem VALUE / expiradas", p)
        self.assertIn("💰 Valor confirmado @ 2,02", p)
        self.assertIn("Odd mínima ≥ 1,51", p)
        self.assertIn("🔴 Sem valor", p)
        self.assertIn("⛔ Expirada", p)
        self.assertIn("não cotações em direto", p)
        # VALUE registado deve aparecer primeiro, independentemente do horário.
        self.assertLess(p.index("Clube 8"), p.index("Clube 4"))
        self.assertLess(p.index("Clube 4"), p.index("Clube 12"))

    def test_nao_mostra_jogos_antigos_ou_dados_invalidos(self):
        passado = exemplo(1, -1)
        outra_data = exemplo(2, 2, data="2030-10-16")
        liquidada = exemplo(3, 3)
        liquidada["estado"] = "liquidado"
        infinito = exemplo(4, 5)
        infinito["probabilidade"] = float("nan")
        p = self._painel([passado, outra_data, liquidada, infinito])
        self.assertIn("Ainda não existem picks Premium", p)
        self.assertNotIn("Clube 1", p)

    def test_status_confirmado_sem_odd_valida_nao_inventa_valor(self):
        incongruente = exemplo(1, 2, estado="confirmado", odd=1.20, minima=1.50)
        p = self._painel([incongruente])
        self.assertIn("🟡 1 sem odd válida", p)
        self.assertNotIn("Valor confirmado @", p)

    def test_nao_forca_value_com_poucas_entradas(self):
        texto = self._painel([exemplo(2, 3, estado="sem_odd", odd=None)])
        self.assertIn("🟢 0 com VALUE registado", texto)
        self.assertIn("A AGUARDAR ODD", texto)
        self.assertNotIn("💰 Valor confirmado @", texto)


if __name__ == "__main__":
    unittest.main()
