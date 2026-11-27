"""V1.4 SHADOW: monitorização documental, sem consultas nem alterar picks."""
import copy
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from main_competicoes import BotPremiumDiarioCompeticoes
from v14_alertas_shadow import _avaliar, relatorio_v14_alertas

NOW = datetime(2026, 11, 27, 19, 57, tzinfo=timezone.utc)
FUTURE = NOW.timestamp() + 7200
PAST = NOW.timestamp() - 86400


def snap(*, odd=2.07, prob=.647, event=401915394, data="2026-10-21",
         kickoff=PAST, estado="liquidada", fonte="OddsPapi / Betano PT"):
    d = {
        "modelo_versao": "V1.2", "event_id": event,
        "casa": "Aston Villa", "fora": "Viking FK",
        "mercado": "Under 3.5 Golos", "liga": "UEFA Champions League",
        "data_jogo": data, "probabilidade": prob, "qualidade": 87,
        "odd_real": odd, "odd_valor_confirmado": odd,
        "valor_confirmado_em": "2026-10-21T18:40:00Z",
        "odds_capturada_em": "2026-10-21T18:40:00Z",
        "odds_atualizada_em": "2026-10-21T18:36:00Z",
        "odds_fonte": fonte, "odds_event_id": "id1000000774165962",
        "timestamp_jogo": kickoff, "estado": estado,
        "criada_em": "2026-10-21T08:00:34Z",
        "diagnostico_modelo": {
            "amostra_casa":8, "amostra_fora":8, "amostra_liga":27,
        },
    }
    return d


def fonte(entradas=None, met=None):
    if entradas is None:
        entradas = [snap()]
    if met is None:
        met = [{"snapshot": 1, "mercado": "Under 3.5 Golos"}]
    return SimpleNamespace(
        dados={"previsoes": entradas},
        metricas_v13_comercial=lambda: {"coorte": met},
    )


class AlertasV14Tests(unittest.TestCase):
    def test_snapshot_399_tem_gap_16pp_e_ev_34pc_sem_recalcular_odds(self):
        lista = [snap(event=i, odd=1.5, prob=.52) for i in range(398)] + [snap()]
        reg = fonte(entradas=lista)
        original = copy.deepcopy(reg.dados)
        texto = relatorio_v14_alertas(reg, "399", agora=NOW)
        self.assertIn("#399", texto)
        self.assertIn("Aston Villa vs Viking FK", texto)
        self.assertIn("2,07", texto)
        self.assertIn("64,7%", texto)
        self.assertIn("48,3%", texto)
        self.assertIn("gap +16,4pp", texto)
        self.assertIn("EV teórico +34,0%", texto)
        self.assertIn("GAP_MODELO_MERCADO_15PP", texto)
        self.assertIn("EV_TEÓRICO_25PC", texto)
        self.assertEqual(reg.dados, original)

    def test_coorte_fixa_nao_alarga_a_candidatos_ou_seleciona_por_resultado(self):
        primeiro = snap()
        terceiro = snap(prob=.48, odd=1.85)
        extra = snap(prob=.82, odd=3.0)
        reg = fonte(entradas=[primeiro,extra,terceiro],met=[
            {"snapshot":1,"mercado":"Under 3.5 Golos"},
            {"snapshot":3,"mercado":"Under 3.5 Golos"},
        ])
        txt = relatorio_v14_alertas(reg, "", agora=NOW)
        self.assertIn("coorte fixa V1.3",txt)
        self.assertIn("Previsões examinadas: 2",txt)
        self.assertIn("Discrepâncias de preço/probabilidade: 1",txt)
        self.assertNotIn("#2",txt)

    def test_previsao_futura_so_antes_jogo_preexistente_e_pendente(self):
        a = snap(data="2026-11-27",kickoff=FUTURE,estado="pendente")
        a["criada_em"]="2026-11-27T18:00:00Z"
        b = snap(data="2026-11-27",kickoff=FUTURE,estado="liquidada")
        c = snap(data="2026-11-27",kickoff=PAST,estado="pendente")
        d = snap(data="2026-11-27",kickoff=FUTURE,estado="pendente")
        d["criada_em"]="2026-11-27T23:00:00Z"
        reg=fonte(entradas=[a,b,c,d])
        txt=relatorio_v14_alertas(reg,"futuros",agora=NOW)
        self.assertIn("Previsões examinadas: 1",txt)
        self.assertIn("#1",txt)
        self.assertNotIn("#2",txt)
        self.assertNotIn("#4",txt)
        self.assertIn("não é uma coorte prospetiva congelada",txt)

    def test_sem_odd_sem_ev_fabricado_e_contagem_correta(self):
        p=snap()
        p["odd_valor_confirmado"]=None
        p["odd_real"]=None
        txt=relatorio_v14_alertas(fonte([p]),"coorte",agora=NOW)
        self.assertIn("Odds guardadas: 0 | Sem odds: 1",txt)
        self.assertNotIn("EV teórico +",txt)
        self.assertIn("sem discrepâncias",txt.lower())

    def test_confirmada_tem_preferencia_sobre_odd_inicial(self):
        p=snap(odd=1.60)
        p["odd_valor_confirmado"]=2.07
        a=_avaliar(1,p)
        self.assertEqual(a["odd"],2.07)
        self.assertIn("GAP_MODELO_MERCADO_15PP",a["alertas"])
        self.assertEqual(a["estado_preco"],"confirmada no snapshot")

    def test_odds_inicial_sem_confirmada_nao_prova_value(self):
        p=snap()
        p["odd_valor_confirmado"]=None
        a=_avaliar(1,p)
        self.assertEqual(a["odd"],2.07)
        self.assertIn("não confirmada para VALUE",a["estado_preco"])

    def test_odds_atualizacao_antiga_e_futura_sao_distintas(self):
        p=snap()
        p["odds_atualizada_em"]="2026-10-20T11:00:00Z"
        a=_avaliar(1,p)
        self.assertIn("ÚLTIMA_ALTERAÇÃO_MAIS_6H",a["alertas"])
        p["odds_atualizada_em"]="2026-10-22T13:00:00Z"
        b=_avaliar(1,p)
        self.assertIn("ALTERAÇÃO_FUTURA",b["alertas"])
        self.assertNotIn("ÚLTIMA_ALTERAÇÃO_MAIS_6H",b["alertas"])

    def test_timestamps_sem_timezone_ou_ausentes_nao_se_assumem_frescos(self):
        p=snap()
        p["odds_atualizada_em"]="2026-10-21T18:36:00"
        self.assertIn("FRESCURA_NÃO_AVALIÁVEL",_avaliar(1,p)["alertas"])
        p["odds_atualizada_em"]=""
        self.assertIn("FRESCURA_NÃO_AVALIÁVEL",_avaliar(1,p)["alertas"])

    def test_multicompeticao_local_reduzida_sem_inferir_legado(self):
        p=snap()
        p["diagnostico_modelo"].update({
            "forma_fonte":"multicompeticao",
            "amostra_casa_local":2,"amostra_fora_local":6,
        })
        self.assertIn("AMOSTRA_LOCAL_REDUZIDA",_avaliar(1,p)["alertas"])
        p["diagnostico_modelo"].pop("amostra_casa_local")
        self.assertNotIn("AMOSTRA_LOCAL_REDUZIDA",_avaliar(1,p)["alertas"])
        txt=relatorio_v14_alertas(fonte([p]),"1",agora=NOW)
        self.assertIn("locais casa/fora: ?/6",txt)

    def test_nome_mercado_e_referencia_na_coorte_devem_coincidir(self):
        p=snap()
        with self.assertRaises(ValueError):
            relatorio_v14_alertas(fonte([p],[{"snapshot":1,"mercado":"Over 2.5 Golos"}]),"",agora=NOW)
        with self.assertRaises(ValueError):
            relatorio_v14_alertas(fonte([p],[{"snapshot":2,"mercado":"Under 3.5 Golos"}]),"",agora=NOW)
        with self.assertRaises(ValueError):
            relatorio_v14_alertas(fonte([p],[{"snapshot":1,"mercado":"Under 3.5 Golos"},{"snapshot":1,"mercado":"Under 3.5 Golos"}]),"",agora=NOW)

    def test_inputs_inseguros_ou_inexistentes_nao_geram_escrita(self):
        reg=fonte()
        antes=copy.deepcopy(reg.dados)
        for arg in ("lixo","-1","1.1","snapshot","snapshot 0","coorte extra"):
            self.assertIn("Uso: /v14_alertas",relatorio_v14_alertas(reg,arg,agora=NOW))
        self.assertIn("inexistente",relatorio_v14_alertas(reg,"999",agora=NOW))
        self.assertEqual(reg.dados,antes)

    def test_sem_oportunidades_nao_inventa(self):
        reg=fonte()
        txt=relatorio_v14_alertas(reg,"futuros",agora=NOW)
        self.assertIn("Previsões examinadas: 0",txt)
        self.assertIn("Sem discrepâncias",txt)

    def test_owner_access_e_ausencia_de_http(self):
        reg=fonte()
        b=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id=b.chat_id=23
        b.username=None
        b.previsoes=reg
        b.enviar_mensagem=Mock()
        b.processar_comando(24,"/v14_alertas coorte",user_id=24)
        b.processar_comando(23,"/v14_alertas 1",user_id=24)
        b.enviar_mensagem.assert_not_called()
        b.processar_comando(23,"/v14_alertas 1",user_id=23)
        b.enviar_mensagem.assert_called_once()
        texto=b.enviar_mensagem.call_args.args[1]
        self.assertIn("V1.4 SHADOW",texto)
        self.assertIn("#1",texto)


if __name__=="__main__":
    unittest.main()
