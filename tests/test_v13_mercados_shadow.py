"""Regressoes do relatorio de mercados da V1.3; nenhuma mutacao ou HTTP."""
import copy
import unittest

from main_competicoes import BotPremiumDiarioCompeticoes
from v13_mercados_shadow import relatorio_mercados_v13


class Registo:
    def __init__(self, previsoes, coorte):
        self.dados = {"previsoes": previsoes}
        self.coorte = coorte

    def metricas_v13_comercial(self):
        return {"coorte": self.coorte, "alvo": 50, "estado": "RECOLHA"}


def caso(i, mercado, y, prob, pnl=None, clv=None):
    return (
        {"mercado": mercado, "probabilidade": prob, "odd_real": 2.0},
        {"snapshot": i, "mercado": mercado, "resultado_binario": y,
         "data_jogo": "2026-11-04", "lucro_unidades": pnl, "clv": clv}
    )


def construir(casos):
    return Registo([x[0] for x in casos], [x[1] for x in casos])


class MercadosV13ShadowTests(unittest.TestCase):
    def test_grupos_disjuntos_e_metricas_exatas(self):
        u = "Under 2.5 Golos"
        o = "Over 2.5 Golos"
        r = construir([caso(1, u, 1, .65, 1.0, .10),
                       caso(2, u, 0, .65, -1.0, 0.0),
                       caso(3, o, 0, .60, -1.0, None)])
        original = copy.deepcopy(r.dados)
        coorte = copy.deepcopy(r.coorte)
        report = relatorio_mercados_v13(r)
        self.assertIn("Entradas auditaveis: 3 | liquidadas: 3", report)
        self.assertIn("Under 2.5 Golos: 2 entradas, 2 liquidadas", report)
        self.assertIn("Acertos 1/2 | ROI +0,0% | P/L 0,00u", report)
        self.assertIn("CLV oficial: 2/2 | medio +5,0%", report)
        self.assertIn("Brier 0,2725", report)
        self.assertIn("Todos os outros: 1 entradas, 1 liquidadas", report)
        self.assertIn("Acertos 0/1 | ROI -100,0%", report)
        self.assertEqual(r.dados, original)
        self.assertEqual(r.coorte, coorte)

    def test_pendentes_nao_contam_para_roi_ou_calibracao(self):
        u = "Under 2.5 Golos"
        r = construir([caso(1, u, None, .90, None, .04),
                       caso(2, u, 1, .70, .70, None)])
        rep = relatorio_mercados_v13(r)
        self.assertIn("Under 2.5 Golos: 2 entradas, 1 liquidadas", rep)
        self.assertIn("Acertos 1/1 | ROI +70,0%", rep)
        self.assertIn("CLV oficial: 1/2 | medio +4,0%", rep)
        self.assertIn("n calib 1", rep)

    def test_entrada_sem_pnl_nao_produz_roi_inventado(self):
        r = construir([caso(1, "Under 2.5 Golos", 0, .7, None)])
        report = relatorio_mercados_v13(r)
        self.assertIn("P/L utilizavel 0/1 (ROI incompleto)", report)
        self.assertNotIn("ROI -", report)

    def test_sem_clv_nao_inventa_media_e_nan_rejeitado(self):
        r = construir([caso(1, "Under 2.5 Golos", 0, float("nan"), -1, float("nan"))])
        rep = relatorio_mercados_v13(r)
        self.assertIn("CLV oficial: 0/1 | media indisponivel", rep)
        self.assertIn("Calibracao indisponivel", rep)

    def test_so_coorte_oficial_duplicados_e_desacordos(self):
        u = "Under 2.5 Golos"
        r = construir([caso(1, u, 0, .65, -1),
                       caso(2, "Over 2.5 Golos", 1, .60, .7)])
        r.coorte = [r.coorte[0], r.coorte[0], {**r.coorte[1], "mercado": u}]
        a = copy.deepcopy(r.dados)
        rep = relatorio_mercados_v13(r)
        self.assertIn("ligacoes invalidas ou inconsistentes: 2", rep)
        self.assertIn("Entradas auditaveis: 1 | liquidadas: 1", rep)
        self.assertIn("Todos os outros: 0 entradas, 0 liquidadas", rep)
        self.assertEqual(a, r.dados)

    def test_limite_grupo_e_segregacao_mercados(self):
        u = "Under 2.5 Golos"
        cases = [caso(i + 1, u, 1 if i % 2 else 0, .65, 0.7 if i % 2 else -1)
                 for i in range(10)]
        r = construir(cases)
        rep = relatorio_mercados_v13(r)
        self.assertIn("Under 2.5 Golos: 10 entradas, 10 liquidadas", rep)
        self.assertNotIn("Under 2.5 Golos: 10 entradas, 10 liquidadas\\n  Acertos 5/10", "")
        self.assertIn("n calib 10", rep)
        self.assertIn("SHADOW", rep)

    def test_sem_alterar_quota_nem_ligar_apis(self):
        r = construir([caso(1, "Ambas Marcam", 1, .7, 0.7)])
        before = copy.deepcopy(r.dados)
        for _ in range(2):
            rep = relatorio_mercados_v13(r)
            self.assertIn("Zero HTTP / zero escrita", rep)
        self.assertEqual(r.dados, before)

    def test_comando_admin_only(self):
        r = construir([caso(1, "Under 2.5 Golos", 1, .65, .7, .01)])
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes = r
        bot.owner_id, bot.chat_id, bot.username = 55, 55, None
        msgs = []
        bot.enviar_mensagem = lambda chat_id, msg: msgs.append((chat_id, msg))
        before = copy.deepcopy(r.dados)
        bot.processar_comando(56, "/v13_mercados", user_id=56)
        self.assertEqual(msgs, [])
        bot.processar_comando(55, "/v13_mercados", user_id=55)
        self.assertEqual(len(msgs), 1)
        self.assertIn("MERCADOS DA V1.3", msgs[0][1])
        self.assertEqual(r.dados, before)


if __name__ == "__main__":
    unittest.main()
