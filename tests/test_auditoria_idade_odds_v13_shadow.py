"""Validação do diagnóstico de timestamps da V1.3, sem chamadas de rede."""
import copy
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from auditoria_idade_odds_v13_shadow import relatorio_idade_odds_v13
from main_competicoes import BotPremiumDiarioCompeticoes


def snap(i, mudou="2026-10-23T22:00:00Z", captura="2026-10-24T10:00:00Z"):
    return {
        "data_jogo": "2026-10-24", "casa": f"Clube {i}", "fora": f"Fora {i}",
        "mercado": "Under 2.5 Golos", "odds_fonte": "OddsPapi / Betano PT",
        "odds_event_id": f"evt-{i}", "odds_atualizada_em": mudou,
        "odds_capturada_em": captura, "valor_confirmado_em": captura,
        "odd_valor_confirmado": 1.80, "odd_real": 1.80,
        "timestamp_jogo": datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc).timestamp(),
    }


def base(lista):
    class Reg:
        def __init__(self):
            self.dados = {"previsoes": lista}
        def metricas_v13_comercial(self):
            return {"alvo": 50, "coorte": [
                {"snapshot": n+1} for n in range(len(self.dados["previsoes"]))
            ]}
    return Reg()


class IdadeOddsV13Tests(unittest.TestCase):
    def test_agregados_sete_preco_inalterado_sem_chamar_api(self):
        arr = [snap(i) for i in range(1, 8)]
        arr += [snap(i, mudou="2026-10-24T09:00:00Z") for i in range(8, 17)]
        original = copy.deepcopy(arr)
        rel = relatorio_idade_odds_v13(base(arr))
        self.assertIn("Entradas: 16 | ≤6h: 9 | 6–24h: 7", rel)
        self.assertIn("#1 Clube 1 vs Fora 1", rel)
        self.assertIn("Idade da alteração: 12,0h", rel)
        self.assertIn("NÃO prova cotação indisponível", rel)
        self.assertNotIn("#16 Clube 16", rel)
        self.assertEqual(arr, original)

    def test_estado_mais_24h_sem_data_e_timestamp_futuro(self):
        arr = [snap(1, mudou="2026-10-22T09:00:00Z"),
               snap(2, mudou=""),
               snap(3, mudou="2026-10-24T13:00:00Z")]
        rel = relatorio_idade_odds_v13(base(arr))
        self.assertIn(">24h: 1", rel)
        self.assertIn("sem comparação: 1", rel)
        self.assertIn("futuras: 1", rel)

    def test_somente_coorte_congelada_e_filtro_por_indice(self):
        arr = [snap(i) for i in range(1, 4)]
        class Fix:
            dados = {"previsoes": arr}
            def metricas_v13_comercial(self):
                return {"alvo": 50, "coorte": [{"snapshot": 2}]}
        rel = relatorio_idade_odds_v13(Fix(), "2")
        self.assertIn("#2 Clube 2 vs Fora 2", rel)
        self.assertNotIn("#1 Clube 1", rel)
        self.assertIn("não pertence às entradas", relatorio_idade_odds_v13(Fix(), "1"))
        self.assertIn("Formato:", relatorio_idade_odds_v13(Fix(), "2,3"))

    def test_owner_only_e_dados_intactos(self):
        arr = [snap(1)]
        reg = base(arr)
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = reg
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        mensagens = []
        bot.enviar_mensagem = lambda chat_id, msg: mensagens.append(msg)
        original = copy.deepcopy(arr)
        bot.processar_comando(52, "/v13_idade_odds", user_id=52)
        self.assertEqual(mensagens, [])
        bot.processar_comando(51, "/v13_idade_odds 1", user_id=51)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("IDADE DAS ODDS", mensagens[0])
        self.assertEqual(arr, original)


if __name__ == "__main__":
    unittest.main()
