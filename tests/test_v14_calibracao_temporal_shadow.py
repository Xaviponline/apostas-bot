"""V1.4 SHADOW: temporalidade, calibração por segmentos e provas passivas de odds."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from v14_calibracao_temporal_shadow import (
    _amostras, _auditar_odds, _avaliar_temporal, _ajustes_segmentados,
    _metricas, _tipo_mercado, _parse_aware, relatorio_v14_calibracao_shadow,
)

PT = ZoneInfo("Europe/Lisbon")


def p(dia, indice, prob=.70, acerto=1, mercado="Under 2.5 Golos",
      liga="Liga A", odd=1.80, versao="V1.2", rank=1):
    inicio = datetime.fromisoformat(dia).replace(tzinfo=PT) + timedelta(hours=19)
    return {
        "modelo_versao": versao, "event_id": 100000+indice,
        "data_jogo": dia, "timestamp_jogo": inicio.timestamp(),
        "ranking_modelo": rank, "casa": "Casa", "fora": "Fora",
        "mercado": mercado, "liga": liga,
        "confianca_modelo": "MÉDIA",
        "probabilidade": prob, "odd_real": odd, "odd_minima": 1.65,
        "estado": ("ganhou" if acerto == 1 else "perdeu" if acerto == 0 else "pendente"),
        "resultado_binario": acerto,
    }


def amostra_dias(dias=50, por_dia=6):
    """Coleção histórica suficiente. Previsão ~70%, observado ~60%."""
    d0=datetime(2026, 9, 1)
    rows=[]
    for dia in range(dias):
        iso=(d0+timedelta(days=dia)).date().isoformat()
        for i in range(por_dia):
            indice=dia*por_dia+i
            rows.append(p(
                iso, indice+1, prob=.7, acerto=int(indice%10<6),
                mercado=("Under 2.5 Golos" if i%2 else "Ambas Marcam"),
                liga=("Liga A" if dia%2 else "Liga B"),
                rank=i+1,
            ))
    return rows


class CalibracaoV14Tests(unittest.TestCase):
    def test_temporal_separa_dias_sem_leakage_e_compara_mesmos_jogos(self):
        dados={"previsoes":amostra_dias()}
        original=copy.deepcopy(dados)
        selecionadas, validas, pend, inco=_amostras(dados)
        self.assertEqual(len(selecionadas),300)
        self.assertEqual(len(validas),300)
        self.assertEqual((pend,inco),(0,0))
        res=_avaliar_temporal(validas)
        self.assertIsNotNone(res)
        self.assertTrue(all(x["data"]<res["corte"] for x in res["treino"]))
        self.assertTrue(all(x["data"]>=res["corte"] for x in res["teste"]))
        self.assertEqual(len(res["treino"])+len(res["teste"]),300)
        self.assertEqual({x["data"] for x in res["treino"]}&
                         {x["data"] for x in res["teste"]},set())
        self.assertLess(res["delta"],0)
        self.assertLess(res["global"]["brier"],res["baseline"]["brier"])
        self.assertEqual(dados,original)

    def test_respostas_de_teste_nao_influenciam_calibradores(self):
        rows=amostra_dias()
        _,validas,_,_=_amostras({"previsoes":rows})
        r1=_avaliar_temporal(validas)
        trocados=copy.deepcopy(validas)
        for row in trocados:
            if row["data"] >= r1["corte"]:
                row["y"]=1-row["y"]
        r2=_avaliar_temporal(trocados)
        self.assertEqual(r1["delta"],r2["delta"])
        self.assertEqual(r1["market"],r2["market"])
        self.assertEqual(r1["liga"],r2["liga"])
        self.assertNotEqual(r1["baseline"]["brier"],r2["baseline"]["brier"])
        self.assertEqual(r1["corte"],r2["corte"])

    def test_poucas_datas_ou_poucas_previsoes_nao_simula(self):
        s=amostra_dias(dias=8,por_dia=8)
        _, r, _,_=_amostras({"previsoes":s})
        self.assertIsNone(_avaliar_temporal(r))
        s=amostra_dias(dias=40,por_dia=2)
        _, r, _,_=_amostras({"previsoes":s})
        self.assertIsNone(_avaliar_temporal(r))
        texto=relatorio_v14_calibracao_shadow({"previsoes":s})
        self.assertIn("Sem amostra temporal suficiente",texto)
        self.assertNotIn("SHADOW Por liga: Brier",texto)

    def test_filtros_top20_versao_e_resultados_incoerentes(self):
        dia="2026-11-27"
        items=[p(dia,i,rank=i) for i in range(1,22)]
        items+=[dict(items[0]),p(dia,100,versao="V1.3",rank=1)]
        items[2]["resultado_binario"]=True
        items[3]["estado"]="pendente"
        items[4]["resultado_binario"]=None
        s,validas,pend,inco=_amostras({"previsoes":items})
        self.assertEqual(len(s),20)
        self.assertEqual(len(validas),17)
        self.assertEqual(pend,1)
        self.assertEqual(inco,2)
        self.assertNotIn("V1.3",relatorio_v14_calibracao_shadow({"previsoes":items}))

    def test_mercado_liga_confiança_separados_sem_inventar(self):
        self.assertEqual(_tipo_mercado("Under 3.5 Golos"),"Under")
        self.assertEqual(_tipo_mercado("Over 2.5 Golos"),"Over")
        self.assertEqual(_tipo_mercado("Ambas Marcam"),"Ambas Marcam")
        self.assertEqual(_tipo_mercado("Vitória Casa"),"Vitória Casa")
        self.assertEqual(_tipo_mercado("Vitória Fora"),"Vitória Fora")
        self.assertEqual(_tipo_mercado("Dupla Hipótese"),"Dupla Hipótese")
        self.assertEqual(_tipo_mercado("Outra escolha"),"Outro")
        txt=relatorio_v14_calibracao_shadow({"previsoes":amostra_dias()})
        self.assertIn("TESTE POR MERCADO",txt)
        self.assertIn("TESTE POR LIGA",txt)
        self.assertIn("TESTE POR CONFIANÇA",txt)
        self.assertIn("SHADOW Global",txt)
        self.assertIn("SHADOW Por mercado",txt)
        self.assertIn("SHADOW Por liga",txt)
        self.assertIn("LogLoss",txt)

    def test_segmentos_pequenos_usam_delta_global(self):
        rows=[
            {"data":f"2026-09-{i+1:02d}", "p":.6, "y":1,
             "mercado":"Under" if i%2 else "Over",
             "liga":"Liga X", "confianca":"ALTA"}
            for i in range(12)
        ]
        ajuste=_ajustes_segmentados(rows,"mercado", -.05)
        self.assertEqual(ajuste,{})
        res=_metricas(rows)
        self.assertGreater(res["brier"],0)
        self.assertGreater(res["logloss"],0)

    def test_ajuste_segmento_usa_shrink_e_limite_seguro(self):
        treino=[
            {"data":f"2026-09-{i//5+1:02d}","p":.6, "y":1,
             "mercado":"Under", "liga":"Liga X", "confianca":"ALTA"}
            for i in range(50)
        ]
        adj=_ajustes_segmentados(treino,"mercado",-.05)
        self.assertIn("Under",adj)
        self.assertTrue(-.15<=adj["Under"]<=.15)
        self.assertLess(adj["Under"],.15)  # shrink para o prior global

    def test_auditoria_odds_sem_fonte_nao_chama_precos_atuais(self):
        t=datetime(2026,11,27,19,tzinfo=PT)
        a=p("2026-11-27",1,odd=1.80)
        b=p("2026-11-27",2,odd=None)
        c=p("2026-11-27",3,odd=1.40)
        d=p("2026-11-27",4,odd=1.87)
        e=p("2026-11-27",5,odd=1.88)
        a["odds_capturada_em"]=(t-timedelta(minutes=40)).isoformat()
        c["odds_capturada_em"]=(t-timedelta(hours=4)).isoformat()
        d["odds_capturada_em"]=(t-timedelta(hours=8)).isoformat()
        e["odds_capturada_em"]=(t+timedelta(minutes=30)).isoformat()
        e["valor_estado"]="expirado"
        cont, faltas=_auditar_odds([a,b,c,d,e])
        self.assertEqual(cont["com_odd"],4)
        self.assertEqual(cont["sem_odd"],1)
        self.assertEqual(cont["captura_ate_2h"],1)
        self.assertEqual(cont["captura_2_6h"],1)
        self.assertEqual(cont["captura_mais_6h"],1)
        self.assertEqual(cont["captura_apos_inicio"],1)
        self.assertEqual(cont["expiradas"],1)
        self.assertEqual(cont["abaixo_minima"],1)
        self.assertEqual(faltas["Under"],1)

    def test_odd_sem_timestamp_informa_sem_provar_disponibilidade(self):
        row=p("2026-11-27",1,odd=1.80)
        row["criada_em"]="2026-11-27T09:00:00+00:00"
        cont,_=_auditar_odds([row])
        self.assertEqual(cont["hora_desconhecida"],1)
        texto=relatorio_v14_calibracao_shadow({"previsoes":[row]})
        self.assertIn("não confirmam disponibilidade atual",texto)
        self.assertIn("Hora de captura desconhecida: 1",texto)
        self.assertIn("Com cotação guardada: 1",texto)
        self.assertNotIn("oportunidade garantida",texto)

    def test_timestamp_sem_timezone_nao_serve_de_evidencia(self):
        self.assertIsNone(_parse_aware("2026-11-27T09:00:00"))
        self.assertIsNone(_parse_aware("garbage"))
        self.assertIsNotNone(_parse_aware("2026-11-27T09:00:00Z"))

    def test_estado_nao_mexe_em_coorte_v13_ou_odds(self):
        dados={"previsoes":amostra_dias(),"coorte_v13":[{"snapshot":1,"stake":1}]}
        original=copy.deepcopy(dados)
        for _ in range(2):
            texto=relatorio_v14_calibracao_shadow(dados)
            self.assertIn("Sem novas APIs",texto)
        self.assertEqual(dados,original)

    def test_comando_owner_sem_http_e_sem_nova_analise(self):
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=43
        bot.username=None
        bot.previsoes=SimpleNamespace(dados={"previsoes":amostra_dias()})
        bot.enviar_mensagem=Mock()
        bot.processar_comando(43,"/v14_calibracao",user_id=43)
        bot.enviar_mensagem.assert_called_once()
        texto=bot.enviar_mensagem.call_args.args[1]
        self.assertIn("V1.4 SHADOW",texto)
        self.assertIn("Corte temporal",texto)
        bot.enviar_mensagem.reset_mock()
        bot.processar_comando(43,"/v14_calibracao",user_id=44)
        bot.processar_comando(44,"/v14_calibracao",user_id=43)
        bot.enviar_mensagem.assert_not_called()


if __name__=="__main__":
    unittest.main()
