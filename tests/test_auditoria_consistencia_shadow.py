"""Teste /consistencia — auditoria apenas leitura, sem chamadas pagas."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from auditoria_consistencia_shadow import relatorio_consistencia
from main_competicoes import BotPremiumDiarioCompeticoes


TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 17, 13, 0, tzinfo=TZ)
DIA = "2030-10-17"


def registo(rank, event_id, mercado, inicio, odd=None, minima=1.50, prob=0.70):
    return {
        "data_jogo": DIA,
        "timestamp_jogo": (AGORA + timedelta(hours=inicio)).timestamp(),
        "event_id": event_id,
        "mercado": mercado,
        "ranking_modelo": rank,
        "casa": f"Casa {event_id}",
        "fora": f"Fora {event_id}",
        "probabilidade": prob,
        "odd_real": odd,
        "odd_minima": minima,
    }


class AuditoriaConsistenciaTest(unittest.TestCase):
    def test_ranking_repetido_nao_confundido_com_duplicate_evento(self):
        items = [
            registo(19, 11, "Under 2.5 Golos", -1, 2.02, 1.51, 0.696),
            registo(19, 12, "Over 2.5 Golos", 3, 1.56, 1.50),
            registo(20, 13, "Ambas Marcam", 5, None),
        ]
        original = copy.deepcopy(items)
        texto = relatorio_consistencia(items, agora=AGORA)
        self.assertIn("Snapshots acumulados: 3", texto)
        self.assertIn("Por começar: 2 | Já iniciados: 1", texto)
        self.assertIn("Rankings repetidos entre snapshots: 1", texto)
        self.assertIn("#19 (2x)", texto)
        self.assertIn("Chaves evento + mercado repetidas: 0", texto)
        self.assertIn("ODDS / EV INVULGARES: 1", texto)
        self.assertIn("Casa 11 vs Fora 11", texto)
        self.assertEqual(items, original)

    def test_mesmo_evento_varios_mercados_e_chave_repetida(self):
        items = [
            registo(1, 99, "Under 2.5 Golos", 3, 1.6),
            registo(2, 99, "Over 2.5 Golos", 3, 1.5),
            registo(3, 99, "Under 2.5 Golos", 3, None),
        ]
        texto = relatorio_consistencia(items, agora=AGORA)
        self.assertIn("Chaves evento + mercado repetidas: 1", texto)
        self.assertIn("Eventos com mercados diferentes: 1", texto)
        self.assertIn("mesma chave evento+mercado", texto)

    def test_dados_nao_finitos_e_datas_distintas_nao_viram_value(self):
        p = registo(1, 12, "Under 3.5 Golos", 2, float("nan"))
        p["timestamp_jogo"] = float("inf")
        anterior = registo(2, 13, "Over 2.5 Golos", 2, 5)
        anterior["data_jogo"] = "2030-10-16"
        texto = relatorio_consistencia([p, anterior], agora=AGORA)
        self.assertIn("Snapshots acumulados: 1", texto)
        self.assertIn("Sem hora fiável: 1", texto)
        self.assertIn("Sem odd: 1", texto)
        self.assertIn("ODDS / EV INVULGARES: 0", texto)

    def test_sem_registos_do_dia(self):
        texto = relatorio_consistencia([], agora=AGORA)
        self.assertIn("sem previsões registadas", texto)
        self.assertIn("Zero", texto if "Zero" in texto else "Zero alterações")

    def test_comando_owner_mostra_relatorio_sem_modificar_registos(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 41
        bot.username = None
        agora = datetime.now(TZ)
        reg = registo(3, 101, "Under 2.5 Golos", 3, 2.02, 1.51, 0.696)
        reg["data_jogo"] = agora.date().isoformat()
        reg["timestamp_jogo"] = (agora + timedelta(hours=3)).timestamp()
        bot.previsoes = SimpleNamespace(dados={"previsoes": [reg]})
        original = copy.deepcopy(bot.previsoes.dados)
        replies = []
        bot.enviar_mensagem = lambda chat, msg: replies.append((chat, msg))
        bot.processar_comando(41, "/consistencia", user_id=41)
        self.assertEqual(len(replies), 1)
        self.assertIn("CONSISTÊNCIA DE SELEÇÕES", replies[0][1])
        self.assertEqual(bot.previsoes.dados, original)
        bot.processar_comando(42, "/consistencia", user_id=42)
        self.assertEqual(len(replies), 1)


if __name__ == "__main__":
    unittest.main()
