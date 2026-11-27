"""Auditoria SHADOW V1.4 — discrepâncias entre PPG e lambda nas vitórias."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from main_competicoes import BotPremiumDiarioCompeticoes
from v14_favoritismo_shadow import avaliar_snapshot, relatorio_v14_favoritismo


def previsao(*, mercado="Vitória Casa", ppg_casa=1.5, ppg_fora=3.0,
             lam_casa=2.408, lam_fora=.756, liga="UEFA Champions League"):
    return {
        "modelo_versao": "V1.2",
        "event_id": 401915383,
        "data_jogo": "2026-11-04",
        "casa": "AEK Athens",
        "fora": "Real Madrid",
        "liga": liga,
        "mercado": mercado,
        "probabilidade": .692,
        "qualidade": 100,
        "diagnostico_modelo": {
            "ppg_casa": ppg_casa, "ppg_fora": ppg_fora,
            "lambda_casa": lam_casa, "lambda_fora": lam_fora,
            "amostra_casa_local": None,
            "amostra_fora_local": None,
        },
        "resultado_binario": 0,
        "odd_real": 11.0,
        "clv_odds": 0.0,
    }


def fonte(previsoes, entradas=None):
    if entradas is None:
        entradas = [{"snapshot": i, "mercado": p["mercado"]}
                    for i,p in enumerate(previsoes,1)]
    return SimpleNamespace(
        dados={"previsoes": previsoes},
        metricas_v13_comercial=lambda: {"coorte": entradas},
    )


class FavoritismoV14Tests(unittest.TestCase):
    def test_aek_real_snapshot_631_aponta_inversao_sem_analise_resultado(self):
        p=previsao()
        a=avaliar_snapshot(631,p)
        self.assertTrue(a["alerta"])
        self.assertAlmostEqual(a["inversao_ppg"],1.5)
        self.assertAlmostEqual(a["vantagem_lambda"],1.652)
        self.assertEqual(a["qualidade"],100)
        reg=fonte([previsao(mercado="Under 2.5 Golos") for _ in range(630)]+[p])
        antigo=copy.deepcopy(reg.dados)
        t=relatorio_v14_favoritismo(reg,"631")
        for esperado in (
            "#631","AEK Athens vs Real Madrid","PPG casa 1.500 | fora 3.000",
            "Lambda casa 2.408 | fora 0.756","Prob. modelo 69.2%",
            "Inversão expressiva: 1/1", "Divergência expressiva",
            "locais casa/fora: ?/?", "Limiares definidos depois",
        ):
            self.assertIn(esperado,t)
        self.assertEqual(reg.dados,antigo)

    def test_mercado_vitoria_fora_inverte_sinais_corretamente(self):
        p=previsao(mercado="Vitória Fora",ppg_casa=3.,ppg_fora=1.5,
                   lam_casa=.75,lam_fora=2.4)
        a=avaliar_snapshot(4,p)
        self.assertTrue(a["alerta"])
        self.assertAlmostEqual(a["inversao_ppg"],1.5)
        self.assertAlmostEqual(a["vantagem_lambda"],1.65)

    def test_ppg_oposto_lambda_sem_dominio_suficiente_nao_sinaliza(self):
        p=previsao(lam_casa=1.20,lam_fora=.75)
        self.assertFalse(avaliar_snapshot(1,p)["alerta"])
        p=previsao(ppg_casa=2.1,ppg_fora=3.0)
        self.assertFalse(avaliar_snapshot(1,p)["alerta"])

    def test_ppg_e_lambdas_sao_medidas_distintas_e_nao_provam_erro(self):
        p=previsao()
        t=relatorio_v14_favoritismo(fonte([p]),"1")
        self.assertIn("São medidas distintas",t)
        self.assertIn("NÃO demonstram erro",t)
        self.assertIn("Qualidade 100 mede cobertura",t)

    def test_coorte_somente_mercados_de_vitoria_nem_todos_os_snapshot(self):
        origem=[previsao(),
                previsao(mercado="Under 3.5 Golos"),
                previsao(mercado="Vitória Casa",ppg_casa=3.,ppg_fora=1.5),
                previsao(mercado="Vitória Fora",ppg_casa=3.0,ppg_fora=1.5,
                         lam_casa=.7,lam_fora=2.1),
                previsao()]
        reg=fonte(origem,[
            {"snapshot":1,"mercado":"Vitória Casa"},
            {"snapshot":2,"mercado":"Under 3.5 Golos"},
            {"snapshot":3,"mercado":"Vitória Casa"},
            {"snapshot":4,"mercado":"Vitória Fora"},
        ])
        t=relatorio_v14_favoritismo(reg,"coorte")
        self.assertIn("Previsões totais: 4 | Mercados de vitória: 3",t)
        self.assertIn("Inversão expressiva: 2/3",t)
        self.assertNotIn("#5",t)

    def test_sem_ppg_historico_nao_inferir(self):
        p=previsao()
        del p["diagnostico_modelo"]["ppg_casa"]
        original=copy.deepcopy(p)
        reg=fonte([p])
        t=relatorio_v14_favoritismo(reg)
        self.assertIn("Dados incompletos: 1",t)
        self.assertIn("sem base avaliável",t)
        self.assertIn("Sem telemetria original suficiente",t)
        self.assertNotIn("PPG casa 1.500",t)
        t=relatorio_v14_favoritismo(reg,"1")
        self.assertIn("Sem telemetria original suficiente",t)
        self.assertEqual(p,original)

    def test_numero_ppg_nan_booleanos_nao_aceites(self):
        p=previsao()
        p["diagnostico_modelo"]["ppg_casa"]=float("nan")
        self.assertFalse(avaliar_snapshot(1,p)["completo"])
        p["diagnostico_modelo"]["ppg_casa"]=True
        self.assertFalse(avaliar_snapshot(1,p)["completo"])

    def test_coorte_divergente_bloqueada(self):
        p=previsao()
        reg=fonte([p],[{"snapshot":1,"mercado":"Vitória Fora"}])
        with self.assertRaises(ValueError):
            relatorio_v14_favoritismo(reg)
        reg=fonte([p],[{"snapshot":1,"mercado":"Vitória Casa"},
                       {"snapshot":1,"mercado":"Vitória Casa"}])
        with self.assertRaises(ValueError):
            relatorio_v14_favoritismo(reg)

    def test_input_invalido_e_snapshot_inexistente_sem_escrita(self):
        reg=fonte([previsao()])
        original=copy.deepcopy(reg.dados)
        for arg in ("lixo","0","snapshot 0","abc","631;cmd","1.0","99999999"):
            self.assertIn("Uso: /v14_favoritismo",relatorio_v14_favoritismo(reg,arg))
        self.assertIn("inexistente",relatorio_v14_favoritismo(reg,"631"))
        self.assertEqual(reg.dados,original)

    def test_owner_exclusivo(self):
        b=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id=b.chat_id=23
        b.username=None
        b.previsoes=fonte([previsao()])
        b.enviar_mensagem=Mock()
        b.processar_comando(24,"/v14_favoritismo coorte",user_id=24)
        b.processar_comando(23,"/v14_favoritismo coorte",user_id=24)
        b.enviar_mensagem.assert_not_called()
        b.processar_comando(23,"/v14_favoritismo coorte",user_id=23)
        b.enviar_mensagem.assert_called_once()
        self.assertIn("PPG × GOLOS ESPERADOS",b.enviar_mensagem.call_args.args[1])


if __name__=="__main__":
    unittest.main()
