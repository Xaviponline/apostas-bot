"""Pesquisa dirigida de fixtures é explícita, isolada e não cria odds."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_investigacao_dirigida import investigar_fixture_por_equipa

PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 16, 21, 22, tzinfo=PT)
TS = datetime(2030, 10, 16, 23, 30, tzinfo=PT).timestamp()


def snapshot(agora=AGORA):
    return {
        "data_jogo": agora.date().isoformat(), "modelo_versao": "V1.2",
        "ranking_modelo": 3, "event_id": 203,
        "timestamp_jogo": agora.timestamp() + 2 * 3600,
        "casa": "Ponte Preta", "fora": "Atlético Goianiense",
        "liga": "Brasileiro Serie B", "mercado": "Under 2.5 Golos",
        "odd_real": None, "odd_minima": 1.51, "estado": "pendente",
    }


def seed(agora=AGORA, participant=22):
    return {
        "id": "seed", "casa": "Ponte Preta", "fora": "Outro Clube",
        "data": agora.isoformat(), "participant1_id": participant,
        "participant2_id": 9999,
    }


class FonteMock:
    provider = "oddspapi"
    configurada = True
    def __init__(self, seeds=None, resultados=None):
        self._eventos_cache = [seed()] if seeds is None else seeds
        self._resultados = [] if resultados is None else resultados
        self.chamadas = []
        self.gerais = 0

    def eventos_hoje(self):
        self.gerais += 1
        return [seed()]

    def _get_papi(self, path, parametros):
        self.chamadas.append((path, dict(parametros)))
        if path != "/fixtures":
            raise AssertionError("Não consultar odds")
        return copy.deepcopy(self._resultados)


def alvo(nome_fora, ts, participant=22):
    return {
        "fixtureId": "fixture-xy",
        "participant1Id": participant, "participant2Id": 1234,
        "participant1Name": "Ponte Preta", "participant2Name": nome_fora,
        "tournamentName": "Brazil Serie B",
        "startTime": datetime.fromtimestamp(ts, PT).isoformat(),
    }


class InvestigacaoDirecionadaTests(unittest.TestCase):
    def test_um_pedido_com_cache_e_pesquisa_exata_somente_fixtures(self):
        previsao = snapshot()
        original = copy.deepcopy(previsao)
        fonte = FonteMock(resultados=[alvo("Atlético Goianiense SAF", previsao["timestamp_jogo"])])
        guardas = []
        def permitir(operacao, reserva):
            guardas.append((operacao, reserva))
            return True
        r = investigar_fixture_por_equipa([previsao], fonte, "3", permitir, agora=AGORA)
        self.assertEqual(guardas, [("ODDS_AUTO", 25)])
        self.assertEqual(fonte.gerais, 0)
        self.assertEqual(len(fonte.chamadas), 1)
        path, params = fonte.chamadas[0]
        self.assertEqual(path, "/fixtures")
        self.assertEqual(params["participantId"], 22)
        self.assertEqual(params["sportId"], 10)
        self.assertNotIn("hasOdds", params)
        self.assertNotIn("statusId", params)
        self.assertIn("Atlético Goianiense SAF", r)
        self.assertIn("horário próximo", r)
        self.assertIn("Sem /odds, sem VALUE", r)
        self.assertEqual(previsao, original)

    def test_sem_quota_sem_consulta(self):
        fonte = FonteMock()
        text = investigar_fixture_por_equipa([snapshot()], fonte, "3", lambda *a: False, agora=AGORA)
        self.assertIn("reserva CLV", text)
        self.assertEqual(fonte.chamadas, [])
        self.assertEqual(fonte.gerais, 0)

    def test_ambiguidade_participant_id_falha_fechado(self):
        fonte = FonteMock(seeds=[seed(participant=22),seed(participant=88)])
        r = investigar_fixture_por_equipa([snapshot()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("mais do que um ID", r)
        self.assertEqual(fonte.chamadas, [])
        self.assertEqual(fonte.gerais, 0)

    def test_sem_cache_no_maximo_uma_descoberta_geral_e_uma_dirigida(self):
        fonte = FonteMock(seeds=[])
        r = investigar_fixture_por_equipa([snapshot()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("lista geral consultada nesta ronda", r)
        self.assertEqual(fonte.gerais, 1)
        self.assertEqual(len(fonte.chamadas), 1)

    def test_nao_repesquisar_previsoes_antigas_ou_apos_inicio(self):
        p = snapshot()
        p["timestamp_jogo"] = AGORA.timestamp() - 60
        fonte = FonteMock()
        r = investigar_fixture_por_equipa([p], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("ainda por começar", r)
        self.assertEqual(fonte.chamadas, [])
        self.assertEqual(fonte.gerais, 0)

    def test_apenas_eventos_do_participante_e_de_hoje(self):
        p = snapshot()
        fonte = FonteMock(resultados=[
            alvo("Atlético Goianiense SAF", p["timestamp_jogo"], participant=77),
            alvo("Clube do dia seguinte", p["timestamp_jogo"] + 24 * 3600),
            alvo("Atlético Goianiense", p["timestamp_jogo"]),
        ])
        r = investigar_fixture_por_equipa([p], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("Eventos da equipa na data do jogo: 1", r)
        self.assertNotIn("Clube do dia seguinte", r)
        self.assertIn("Atlético Goianiense", r)

    def test_admin_apenas_repeticoes_nunca_consultam_outra_vez(self):
        agora = datetime.now(PT)
        p = snapshot(agora=agora)
        p["timestamp_jogo"] = (agora + timedelta(hours=2)).timestamp()
        fonte = FonteMock(seeds=[seed(agora=agora)], resultados=[])
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = 42
        bot.chat_id = 42
        bot.username = None
        bot.previsoes = SimpleNamespace(dados={"previsoes": [p]})
        bot.odds = fonte
        bot._investigacoes_dirigidas_cache = {}
        bot._quota_permite_captura = lambda *args: True
        mensagens = []
        bot.enviar_mensagem = lambda chat, msg: mensagens.append((chat, msg))
        copia = copy.deepcopy(bot.previsoes.dados)
        with patch("odds_auditoria.AuditoriaOdds.enriquecer",
                   side_effect=AssertionError("Não modificar odds")):
            bot.processar_comando(43, "/odds_investigar 3", user_id=43)
            bot.processar_comando(42, "/odds_investigar 3", user_id=42)
            bot.processar_comando(42, "/odds_investigar 3", user_id=42)
        self.assertEqual(len(mensagens), 2)
        self.assertIn("PESQUISA DIRIGIDA ODDS", mensagens[0][1])
        self.assertIn("sem novos pedidos", mensagens[1][1])
        self.assertEqual(len(fonte.chamadas), 1)
        self.assertEqual(copia, bot.previsoes.dados)

    def test_formato_invalido_nao_faz_consultas(self):
        fonte = FonteMock()
        r = investigar_fixture_por_equipa([snapshot()], fonte, "3 abrir", lambda *a: True, agora=AGORA)
        self.assertIn("Formato", r)
        self.assertEqual(fonte.chamadas, [])


if __name__ == "__main__":
    unittest.main()
