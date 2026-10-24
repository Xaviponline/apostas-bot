"""Regressao de calibracao SHADOW da coorte V1.3 fixa."""
import copy
import unittest
from types import SimpleNamespace

from main_competicoes import BotPremiumDiarioCompeticoes
from v13_calibracao_shadow import relatorio_calibracao_v13


class Reg:
    def __init__(self, previsoes, indices=None, estado="RECOLHA"):
        self.dados = {"previsoes": previsoes}
        self.indices = indices or list(range(1, len(previsoes) + 1))
        self.estado = estado

    def metricas_v13_comercial(self):
        return {
            "coorte": [
                {
                    "snapshot": i,
                    "resultado_binario": self.dados["previsoes"][i - 1].get("resultado_binario"),
                    "mercado": self.dados["previsoes"][i - 1].get("mercado"),
                    "data_jogo": self.dados["previsoes"][i - 1].get("data_jogo"),
                }
                for i in self.indices
            ],
            "alvo": 50,
            "estado": self.estado,
        }


def caso(prob, result, mercado="Under 2.5 Golos", data="2026-10-24"):
    return {
        "probabilidade": prob,
        "resultado_binario": result,
        "mercado": mercado,
        "data_jogo": data,
        "odd_real": 1.91,
    }


class CalibracaoV13ShadowTests(unittest.TestCase):
    def test_calibracao_global_exata_e_dados_intactos(self):
        dados = [caso(.60, 1), caso(.80, 0)]
        reg = Reg(dados)
        antes = copy.deepcopy(reg.dados)
        rel = relatorio_calibracao_v13(reg)
        self.assertIn("Acertos observados: 1/2 (50,0%)", rel)
        self.assertIn("Probabilidade media prevista: 70,0%", rel)
        self.assertIn("Acertos esperados pelo modelo: 1,40", rel)
        self.assertIn("Diferenca real − previsto: -20,0pp", rel)
        self.assertIn("Brier Score na coorte: 0,4000", rel)
        self.assertIn("amostra pequena (<10)", rel)
        self.assertEqual(reg.dados, antes)

    def test_pendentes_nunca_contam_como_perdas(self):
        reg = Reg([caso(.70, None), caso(.80, 1)])
        rel = relatorio_calibracao_v13(reg)
        self.assertIn("Liquidadas com probabilidade valida: 1 | pendentes: 1", rel)
        self.assertIn("Acertos observados: 1/1 (100,0%)", rel)

    def test_nada_liquidado_sem_brier_inventado(self):
        rel = relatorio_calibracao_v13(Reg([caso(.70, None)]))
        self.assertIn("Sem resultados suficientes", rel)
        self.assertNotIn("Brier Score na coorte", rel)

    def test_apenas_coorte_fixa_sem_entradas_rejeitadas(self):
        itens = [
            caso(.20, 0),
            caso(.55, 1),
            caso(.90, 1),
        ]
        reg = Reg(itens, indices=[2])
        rel = relatorio_calibracao_v13(reg)
        self.assertIn("Coorte oficial: 1/50", rel)
        self.assertIn("Probabilidade media prevista: 55,0%", rel)
        self.assertIn("Acertos observados: 1/1", rel)

    def test_probabilidade_malformada_e_duplicate_snapshot_seguranca(self):
        itens = [
            caso(float("nan"), 1),
            caso(.90, 0),
        ]
        class RegInconsistente(Reg):
            def metricas_v13_comercial(self):
                d = super().metricas_v13_comercial()
                d["coorte"].append(d["coorte"][1].copy())
                return d

        reg = RegInconsistente(itens)
        rel = relatorio_calibracao_v13(reg)
        self.assertIn("dados incompletos: 2", rel)
        self.assertIn("Liquidadas com probabilidade valida: 1", rel)
        self.assertIn("Acertos esperados pelo modelo: 0,90", rel)

    def test_segmento_descritivo_a_partir_de_dez_resultados(self):
        itens = [caso(.65, 1 if i % 2 else 0, "Over 2.5 Golos",
                       f"2026-10-{i+10:02}") for i in range(10)]
        rel = relatorio_calibracao_v13(Reg(itens))
        self.assertIn("Over 2.5 Golos: n=10 | esperado 65,0% | real 50,0%", rel)
        self.assertIn("Calibracao nao prova rentabilidade", rel)

    def test_owner_only_zero_mutacoes(self):
        dados = [caso(.75, 1)]
        reg = Reg(dados)
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = reg
        bot.owner_id, bot.chat_id, bot.username = 55, 55, None
        mensagens = []
        bot.enviar_mensagem = lambda chat_id, msg: mensagens.append((chat_id, msg))
        anterior = copy.deepcopy(reg.dados)
        bot.processar_comando(56, "/v13_calibracao", user_id=56)
        self.assertEqual(mensagens, [])
        bot.processar_comando(55, "/v13_calibracao", user_id=55)
        self.assertEqual(len(mensagens), 1)
        self.assertIn("CALIBRACAO V1.3", mensagens[0][1])
        self.assertEqual(reg.dados, anterior)


if __name__ == "__main__":
    unittest.main()
