"""Quarentena U19 confirmada com TFF, sem alterar snapshots nem V1.3."""
import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fixture_guard_shadow import (
    juventude_confirmada_hoje, categorias_incompativeis, categoria_juvenil,
)
from odds_auditoria import AuditoriaOdds
from scout_shadow import _possiveis
from main_competicoes import BotPremiumDiarioCompeticoes

PT = ZoneInfo("Europe/Lisbon")
TS = datetime(2026, 10, 24, 13, tzinfo=PT).timestamp()
HOJE = datetime(2026, 10, 24, 9, 50, tzinfo=PT)


def snap(casa="Eyupspor", fora="Kasimpasa", liga="Turkish Super Lig", dia="2026-10-24", ts=TS):
    return {
        "casa": casa, "fora": fora, "liga": liga, "data_jogo": dia,
        "timestamp_jogo": ts, "ranking_modelo": 2,
        "estado": "pendente", "probabilidade": .74, "odd_minima": 1.50,
        "qualidade": 87, "mercado": "Under 2.5 Golos",
        "odd_real": 1.85, "odd_valor_confirmado": 1.85,
        "valor_estado": "confirmado",
    }


class Relogio:
    @staticmethod
    def now(tz=None):
        return HOJE.astimezone(tz) if tz else HOJE


class FonteU19:
    nome_fonte = "FonteFake"
    configurada = True

    def __init__(self, liga_evento):
        self.liga_evento = liga_evento
        self.odds_calls = 0

    def eventos_hoje(self):
        return [{
            "id": "EVENT", "casa": "Eyupspor", "fora": "Kasimpasa",
            "liga": self.liga_evento,
            "data": "2030-10-24T12:00:00Z",
        }]

    def odds_evento(self, event_id):
        self.odds_calls += 1
        return {
            "id": "EVENT", "casa": "Eyupspor", "fora": "Kasimpasa",
            "liga": "U19 PAF Ligi",
            "fonte": self.nome_fonte,
            "mercados": [{
                "name": "Total Goals", "period": "fulltime",
                "odds": [{"seleção": "Under 2.5", "odd": 1.85}],
            }],
        }


class QuarentenaU19Tests(unittest.TestCase):
    def test_os_tres_encontros_tff_rejeitados(self):
        self.assertTrue(juventude_confirmada_hoje(snap()))
        self.assertTrue(juventude_confirmada_hoje(snap("Gaziantep FK", "Erzurum BB")))
        self.assertTrue(juventude_confirmada_hoje(snap("Samsunspor", "Amed SFK")))

    def test_nao_bloqueia_liga_senior_ou_datas_futuras(self):
        self.assertFalse(juventude_confirmada_hoje(snap("Galatasaray","Besiktas")))
        self.assertFalse(juventude_confirmada_hoje(snap(dia="2026-10-25")))
        self.assertFalse(juventude_confirmada_hoje(snap(liga="U19 PAF Ligi")))
        self.assertFalse(juventude_confirmada_hoje(snap(casa="Kasimpasa",fora="Eyupspor")))
        self.assertFalse(juventude_confirmada_hoje(None))

    def test_categorias_explicitas_e_senior_senior(self):
        self.assertTrue(categoria_juvenil("U19 PAF Ligi"))
        self.assertTrue(categoria_juvenil("Under-21 Cup"))
        self.assertFalse(categoria_juvenil("Turkish Super Lig"))
        self.assertFalse(categorias_incompativeis("Turkish Super Lig", "Super Lig"))
        self.assertFalse(categorias_incompativeis("Turkish Super Lig", None))
        self.assertTrue(categorias_incompativeis("Turkish Super Lig","U19 PAF Ligi"))
        self.assertFalse(categorias_incompativeis("U19 PAF Ligi","U19 Youth League"))

    def test_alerta_liga_juvenil_e_diagnostico_antes_de_odds(self):
        fonte = FonteU19("U19 PAF Ligi")
        aud = AuditoriaOdds(fonte)
        jogo = {"id":123,"casa":"Eyupspor","fora":"Kasimpasa",
                "liga":"Turkish Super Lig",
                "timestamp":datetime(2030, 10, 24, 12, tzinfo=timezone.utc).timestamp()}
        original = {"jogo": jogo, "mercado": "Under 2.5 Golos", "probabilidade": .70}
        antes = copy.deepcopy(original)
        res = aud.enriquecer([original])[0]
        self.assertEqual(original, antes)
        self.assertNotIn("odd_real", res)
        self.assertEqual(res["_odds_diag"], "liga_idade_incompativel")
        self.assertEqual(fonte.odds_calls, 0)

    def test_categoria_juvenil_so_no_payload_tambem_bloqueia(self):
        fonte = FonteU19("Turkish Super Lig")
        aud = AuditoriaOdds(fonte)
        jogo = {"id":123,"casa":"Eyupspor","fora":"Kasimpasa",
                "liga":"Turkish Super Lig",
                "timestamp":datetime(2030, 10, 24, 12, tzinfo=timezone.utc).timestamp()}
        res = aud.enriquecer([{"jogo":jogo,"mercado":"Under 2.5 Golos",
                               "probabilidade":.70}])[0]
        self.assertEqual(fonte.odds_calls,1)
        self.assertNotIn("odd_real",res)
        self.assertEqual(res["_odds_diag"],"liga_idade_incompativel")

    def test_scout_rejeita_sem_consultar_odds(self):
        candidatos, causas = _possiveis([snap(), snap("Samsunspor","Amed SFK"),
                                         snap("Gaziantep FK","Erzurum BB")], HOJE)
        self.assertEqual(candidatos,[])
        self.assertEqual(causas["fixture_u19_confirmado_tff"],3)

    def test_vitrine_omite_tres_e_preserva_historico(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        outros = snap("Porto", "Benfica", liga="Portuguese Primeira Liga")
        todos = [snap(),snap("Samsunspor","Amed SFK"),
                 snap("Gaziantep FK","Erzurum BB"),outros]
        bot.previsoes=SimpleNamespace(dados={"previsoes":todos})
        original=copy.deepcopy(todos)
        with patch("main_competicoes.datetime",Relogio):
            out=bot._executar_picks_cliente()
        self.assertNotIn("Samsunspor vs",out)
        self.assertNotIn("Eyupspor",out)
        self.assertNotIn("Gaziantep FK",out)
        self.assertIn("Porto",out)
        self.assertIn("3 previsao(oes) U19 TFF ocultada(s)",out)
        self.assertEqual(todos,original)

    def test_vitrine_so_u19_gera_explicitamente_aviso(self):
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.previsoes=SimpleNamespace(dados={"previsoes":[snap()]})
        with patch("main_competicoes.datetime", Relogio):
            out=bot._executar_picks_cliente()
        self.assertIn("Ainda não existem picks Premium",out)
        self.assertIn("1 previsao(oes) U19 confirmada(s)",out)


if __name__ == "__main__":
    unittest.main()
