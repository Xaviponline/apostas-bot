"""V1.4 SHADOW: telemetria adicional sem alterar a lógica das previsões."""
import copy
import math
import unittest

from analisador_inteligente import AnalisadorInteligente
from estatisticas_espn_resiliente import EstatisticasESPNResiliente
from modelo_snapshot_shadow import diagnostico_snapshot
from previsoes_premium import RegistoPrevisoes


def partida(i, casa, fora, gc=2, gf=1):
    return {
        "id": i, "timestamp": float(10000-i),
        "casa_id": casa, "fora_id": fora,
        "golos_casa": gc, "golos_fora": gf,
    }


def forma_equipa(team, raiz):
    # Quatro jogos em casa e quatro fora para cada equipa.
    return [
        partida(raiz+i, team if i%2==0 else raiz+i+1000,
                raiz+i+1000 if i%2==0 else team,
                gc=2 if i%3 else 1, gf=1 if i%3 else 2)
        for i in range(8)
    ]


def entrada():
    stats = EstatisticasESPNResiliente()
    stats._formas_globais = {101: forma_equipa(101,100),
                             202: forma_equipa(202,300)}
    liga = [partida(500+i,1000+i,2000+i,2,1) for i in range(27)]
    jogo = {
        "id": 401915394, "casa": "Casa", "fora": "Fora",
        "casa_id": 101, "fora_id": 202,
        "liga": "UEFA Champions League", "league_code": "uefa.champions",
    }
    return stats.analisar_jogo(jogo,liga),stats,liga,jogo


class TelemetriaFormaV14Tests(unittest.TestCase):
    def test_amostras_extra_sao_as_mesmas_ja_usadas_na_forma(self):
        a,stats,liga,jogo=entrada()
        self.assertIsNotNone(a)
        self.assertEqual(a["amostra_casa"],8)
        self.assertEqual(a["amostra_fora"],8)
        self.assertEqual(a["amostra_liga"],27)
        self.assertEqual(a["amostra_casa_local"],4)
        self.assertEqual(a["amostra_fora_local"],4)
        self.assertEqual(a["amostra_casa_efetiva"],4)
        self.assertEqual(a["amostra_fora_efetiva"],4)
        self.assertEqual(a["qualidade"],87)
        self.assertEqual(a["forma_fonte"],"multicompeticao")
        self.assertEqual(a["media_liga_casa"],2.0)
        self.assertEqual(a["media_liga_fora"],1.0)
        p=stats._probabilidades(a["lambda_casa"],a["lambda_fora"])
        self.assertAlmostEqual(a["probabilidades"]["Under 3.5 Golos"],p["Under 3.5 Golos"])
        self.assertAlmostEqual(
            a["lambda_casa"],
            a["media_modelo_casa_gf"]*a["media_modelo_fora_ga"]/a["media_liga_casa"],
        )
        self.assertAlmostEqual(
            a["lambda_fora"],
            a["media_modelo_fora_gf"]*a["media_modelo_casa_ga"]/a["media_liga_fora"],
        )

    def test_conservador_e_ranking_ficam_iguais(self):
        a,_,_,_=entrada()
        selecionar=AnalisadorInteligente()
        velho={k:v for k,v in a.items() if k not in (
            "amostra_casa_local","amostra_fora_local",
            "amostra_casa_efetiva","amostra_fora_efetiva",
            "media_liga_casa","media_liga_fora","media_modelo_casa_gf",
            "media_modelo_casa_ga","media_modelo_fora_gf","media_modelo_fora_ga"
        )}
        novo=selecionar._melhor_selecao(a)
        original=selecionar._melhor_selecao(velho)
        for campo in ("mercado","probabilidade","probabilidade_bruta",
                      "qualidade","ranking_modelo","score","odd_minima"):
            self.assertEqual(novo.get(campo),original.get(campo),campo)
        self.assertEqual(novo["confianca"],original["confianca"])

    def test_novo_snapshot_guarda_apenas_proveniencia_reconhecida(self):
        a,_,_,_=entrada()
        antes=copy.deepcopy(a)
        d=RegistoPrevisoes._snapshot_diagnostico(a)
        self.assertEqual(a,antes)
        self.assertEqual(d["forma_fonte"],"multicompeticao")
        self.assertEqual(d["amostra_casa_local"],4)
        self.assertEqual(d["amostra_fora_local"],4)
        self.assertEqual(d["amostra_casa_efetiva"],4)
        self.assertEqual(d["amostra_fora_efetiva"],4)
        self.assertEqual(d["amostra_liga"],27)
        self.assertEqual(d["media_liga_casa"],2.0)
        with_unknown={**a,"forma_fonte":"legado_inferido"}
        self.assertNotIn("forma_fonte",RegistoPrevisoes._snapshot_diagnostico(with_unknown))

    def test_visualizacao_nova_com_campos_e_legacy_honesto(self):
        a,_,_,_=entrada()
        d=RegistoPrevisoes._snapshot_diagnostico(a)
        registro={
            "casa":"Casa","fora":"Fora","event_id":401915394,
            "mercado":"Under 3.5 Golos","data_jogo":"2026-10-21",
            "probabilidade":.647,"probabilidade_bruta":.684,
            "qualidade":87,"diagnostico_modelo":d,
        }
        texto=diagnostico_snapshot({"previsoes":[registro]},"401915394")
        self.assertIn("Amostras locais: casa 4 | fora 4",texto)
        self.assertIn("Amostras usadas no cálculo: casa 4 | fora 4",texto)
        self.assertIn("Forma: multicompetição",texto)
        self.assertIn("Média da competição: golos casa 2,000 | fora 1,000",texto)
        antigo=copy.deepcopy(registro)
        for campo in ("amostra_casa_local","amostra_fora_local",
                      "amostra_casa_efetiva","amostra_fora_efetiva",
                      "forma_fonte","media_liga_casa","media_liga_fora"):
            antigo["diagnostico_modelo"].pop(campo,None)
        texto=diagnostico_snapshot({"previsoes":[antigo]},"401915394")
        self.assertIn("Amostras locais: casa não registado",texto)
        self.assertIn("Amostras usadas no cálculo: casa não registado",texto)
        self.assertIn("Forma: não registada",texto)
        self.assertIn("Média da competição: golos casa não registado",texto)
        self.assertNotIn("Amostras locais: casa 4",texto)

    def test_nao_reconstroi_telemetria_legada_ou_reescreve_o_dataset(self):
        a,_,_,_=entrada()
        historico={"previsoes":[{
            "event_id":401915394,
            "mercado":"Under 3.5 Golos",
            "casa":"Casa","fora":"Fora",
            "probabilidade":.647,"probabilidade_bruta":.684,
            "diagnostico_modelo":{
                "amostra_casa":8,"amostra_fora":8,"amostra_liga":27
            },
        }]}
        antes=copy.deepcopy(historico)
        rep=diagnostico_snapshot(historico,"401915394")
        self.assertIn("não registado",rep)
        self.assertEqual(historico,antes)


if __name__=="__main__":
    unittest.main()
