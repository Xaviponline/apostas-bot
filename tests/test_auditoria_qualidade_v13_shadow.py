"""Auditoria V1.3 separada: não toca na coorte oficial."""
import copy
import unittest
from types import SimpleNamespace

from auditoria_qualidade_v13_shadow import relatorio_qualidade_v13
from main_competicoes import BotPremiumDiarioCompeticoes


def pick(casa, fora, **kwargs):
    p = {
        "data_jogo": "2026-10-24", "casa": casa, "fora": fora,
        "liga": "Turkish Super Lig", "timestamp_jogo": 1792857600,
        "odds_event_id": "111", "odds_atualizada_em": "2026-10-24T09:55:00Z",
        "odds_capturada_em": "2026-10-24T10:00:00Z",
        "odd_fecho": 1.55, "odd_fecho_capturada_em": "2026-10-24T15:40:00Z",
    }
    p.update(kwargs)
    return p


def reg(picks):
    return SimpleNamespace(
        dados={"previsoes": picks},
        metricas_v13_comercial=lambda: {
            "alvo": 50,
            "coorte": [{"snapshot": i + 1} for i in range(len(picks))]
        },
    )


class V13QualidadeTests(unittest.TestCase):
    def test_alerta_u19_sem_apagar_entradas(self):
        picks = [
            pick("Eyupspor", "Kasimpasa"),
            pick("Porto", "Braga", liga="Portuguese Primeira Liga",
                 odd_fecho=None),
        ]
        antes = copy.deepcopy(picks)
        rel = relatorio_qualidade_v13(reg(picks))
        self.assertIn("Entradas auditadas: 2/50", rel)
        self.assertIn("fixture_u19_confirmado: 1", rel)
        self.assertIn("Snapshot #1 Eyupspor vs Kasimpasa", rel)
        self.assertEqual(picks, antes)

    def test_preco_antigo_e_fecho_fora_da_janela_sao_so_alerta(self):
        picks = [pick("Porto", "Braga",
                      liga="Portuguese Primeira Liga",
                      odds_atualizada_em="2026-10-23T00:00:00Z",
                      odd_fecho_capturada_em="2026-10-24T17:00:00Z")]
        texto = relatorio_qualidade_v13(reg(picks))
        self.assertIn("odd_desatualizada: 1", texto)
        self.assertIn("fecho_fora_janela_t30: 1", texto)

    def test_integridade_sem_metadados_legados_nao_inventa(self):
        texto = relatorio_qualidade_v13(reg([{}]))
        self.assertIn("id_fixture_odds_ausente: 1", texto)
        self.assertIn("hora_captura_entrada_ausente: 1", texto)
        self.assertIn("historicos legados", texto)

    def test_comando_admin_only_e_readonly(self):
        dados = [pick("Porto", "Braga", liga="Portuguese Primeira Liga")]
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = reg(dados)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        mensagens = []
        bot.enviar_mensagem = lambda chat_id, msg: mensagens.append(msg)
        antes = copy.deepcopy(dados)
        bot.processar_comando(52, "/v13_qualidade", user_id=52)
        self.assertEqual(mensagens, [])
        bot.processar_comando(51, "/v13_qualidade", user_id=51)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("QUALIDADE DA COORTE V1.3", mensagens[0])
        self.assertEqual(dados, antes)


if __name__ == "__main__":
    unittest.main()
