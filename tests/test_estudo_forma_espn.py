"""Testes offline: identidade do fixture, dois pedidos máximos e sem leakage."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests

from estudo_forma_espn import contexto_espn
from main_competicoes import BotPremiumDiarioCompeticoes


TZ_PT = ZoneInfo("Europe/Lisbon")
CRIADA = datetime(2030, 10, 16, 9, tzinfo=timezone.utc)
KICKOFF = datetime(2030, 10, 16, 19, tzinfo=timezone.utc)


def snapshot():
    return {
        "event_id": 1000,
        "data_jogo": "2030-10-16",
        "timestamp_jogo": KICKOFF.timestamp(),
        "criada_em": CRIADA.isoformat(),
        "casa": "Casa Real",
        "fora": "Visitante Real",
        "modelo_versao": "V1.2",
        "ranking_modelo": 1,
        "mercado": "Over 2.5 Golos",
        "probabilidade": 0.68,
        "diagnostico_modelo": {"liga_codigo": "fra.1"},
    }


def event(id, day, home_id=101, away_id=202, gols_home=2, gols_away=1,
          finished=True, home_name="Casa Real", away_name="Visitante Real"):
    return {
        "id": str(id),
        "date": f"{day}T19:00:00Z",
        "status": {"type": {"state": "post" if finished else "pre", "completed": finished}},
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"id": str(home_id), "displayName": home_name}, "score": str(gols_home)},
                {"homeAway": "away", "team": {"id": str(away_id), "displayName": away_name}, "score": str(gols_away)},
            ],
        }],
    }


class Resposta:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP inválido", response=self)

    def json(self):
        return self.payload


class Sessao:
    def __init__(self, fixture=None, historico=None, status=200):
        self.calls = []
        self.fixture = fixture if fixture is not None else [event(1000, "2030-10-16", finished=False)]
        self.historico = historico if historico is not None else [
            event(41, "2030-10-12", home_id=101, away_id=303, home_name="Casa Real", away_name="Rival A"),
            event(42, "2030-10-11", home_id=404, away_id=202, home_name="Rival B", away_name="Visitante Real", gols_home=0, gols_away=2),
            event(43, "2030-10-07", home_id=202, away_id=101, home_name="Visitante Real", away_name="Casa Real", gols_home=1, gols_away=2),
            # Mesmo equipa, mas resultado futuro ao snapshot: excluir sempre.
            event(44, "2030-10-17", home_id=101, away_id=303, home_name="Casa Real", away_name="Rival A"),
        ]
        self.status = status

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if len(self.calls) > 2:
            raise AssertionError("O contexto nunca pode ultrapassar 2 pedidos ESPN")
        if "dates" not in (params or {}):
            raise AssertionError("Consulta sem intervalo de datas")
        return Resposta({"events": self.fixture if len(self.calls) == 1 else self.historico}, self.status)


class EstudoFormaEspnTests(unittest.TestCase):
    def test_conteudo_verificado_sem_futuros_e_ate_dois_pedidos(self):
        s = Sessao()
        p = snapshot()
        original = copy.deepcopy(p)
        texto = contexto_espn(p, session=s)
        self.assertIn("FORMA RECENTE — ESPN", texto)
        self.assertIn("Casa Real — até 5 resultados", texto)
        self.assertIn("Visitante Real — até 5 resultados", texto)
        self.assertIn("12/10 (C) vs Rival A: 2-1", texto)
        self.assertIn("11/10 (F) vs Rival B: 2-0", texto)
        self.assertIn("Confrontos diretos na janela: 1", texto)
        self.assertNotIn("17/10", texto)
        self.assertEqual(len(s.calls), 2)
        self.assertEqual(s.calls[0][1]["dates"], "20301016")
        self.assertEqual(s.calls[1][1]["dates"], "2030")
        self.assertIn("07/08/2030 a 15/10/2030", texto)
        self.assertTrue(all(x[0].endswith("/fra.1/scoreboard") for x in s.calls))
        self.assertTrue(all(x[2] == (4, 12) for x in s.calls))
        self.assertEqual(p, original)

    def test_event_id_nao_corresponde_nao_consulta_historico(self):
        s = Sessao(fixture=[event(777, "2030-10-16")])
        texto = contexto_espn(snapshot(), session=s)
        self.assertIn("não confirmado pelo ID", texto)
        self.assertEqual(len(s.calls), 1)

    def test_kickoff_divergente_nao_consulta_historico(self):
        s = Sessao(fixture=[event(1000, "2030-10-17")])
        texto = contexto_espn(snapshot(), session=s)
        self.assertIn("horário do fixture não validados", texto)
        self.assertEqual(len(s.calls), 1)

    def test_payload_competidor_corrompido_nao_produz_associacao(self):
        fixture = event(1000, "2030-10-16", finished=False)
        fixture["competitions"][0]["competitors"] = [None, {}]
        sessao = Sessao(fixture=[fixture])
        self.assertIn("Equipas ou horário", contexto_espn(snapshot(), session=sessao))
        self.assertEqual(len(sessao.calls), 1)

    def test_liga_invalida_e_criacao_ausente_falham_sem_rede(self):
        p = snapshot()
        p["diagnostico_modelo"]["liga_codigo"] = "fra.1/../../leak"
        s = Sessao()
        self.assertIn("inválido", contexto_espn(p, session=s))
        self.assertEqual(s.calls, [])
        p = snapshot()
        p.pop("criada_em")
        self.assertIn("Sem data de criação", contexto_espn(p, session=s))
        self.assertEqual(s.calls, [])

    def test_http_e_api_truncada_sao_inconclusivos(self):
        self.assertIn("calendário do jogo: HTTP 503", contexto_espn(snapshot(), session=Sessao(status=503)))
        s = Sessao(historico=[event(42+i, "2030-10-10") for i in range(500)])
        self.assertIn("truncado", contexto_espn(snapshot(), session=s))
        self.assertEqual(len(s.calls), 2)

    def test_pedido_maior_que_500_recupera_forma_sem_terceiro_pedido(self):
        historico = [
            event(
                2000 + i, "2030-10-10",
                home_id=101 if i == 0 else 5000 + i,
                away_id=303 if i == 0 else 7000 + i,
                home_name="Casa Real" if i == 0 else f"Casa {i}",
                away_name="Rival A" if i == 0 else f"Fora {i}",
            ) for i in range(600)
        ]
        s = Sessao(historico=historico)
        original = copy.deepcopy(snapshot())
        texto = contexto_espn(original, session=s)
        self.assertIn("10/10 (C) vs Rival A: 2-1", texto)
        self.assertNotIn("truncado", texto)
        self.assertEqual(len(s.calls), 2)
        self.assertEqual(s.calls[1][1]["limit"], 1000)
        self.assertEqual(original, snapshot())

    def test_limite_1000_atingido_ainda_suspende_com_seguranca(self):
        historico = [event(5000 + i, "2030-10-10") for i in range(1000)]
        s = Sessao(historico=historico)
        detalhes = {}
        texto = contexto_espn(snapshot(), session=s, detalhes=detalhes)
        self.assertIn("potencialmente truncado", texto)
        self.assertEqual(detalhes, {})
        self.assertEqual(len(s.calls), 2)

    def test_http_400_no_historico_identifica_fase_sem_dados_sensiveis(self):
        class Historico400(Sessao):
            def get(self, url, params=None, timeout=None):
                r = super().get(url, params=params, timeout=timeout)
                if len(self.calls) == 2:
                    return Resposta({"message": "segredo interno do fornecedor"}, status=400)
                return r

        sessao = Historico400()
        texto = contexto_espn(snapshot(), session=sessao)
        self.assertIn("histórico do ano: HTTP 400", texto)
        self.assertNotIn("segredo interno", texto)
        self.assertNotIn("https://", texto)
        self.assertEqual(len(sessao.calls), 2)
        self.assertEqual(sessao.calls[1][1]["dates"], "2030")

    def test_ano_civil_nao_importa_resultados_do_ano_anterior(self):
        p = snapshot()
        p["timestamp_jogo"] = datetime(2030, 1, 20, 19, tzinfo=timezone.utc).timestamp()
        p["criada_em"] = datetime(2030, 1, 20, 9, tzinfo=timezone.utc).isoformat()
        fixture = event(1000, "2030-01-20", finished=False)
        sessao = Sessao(
            fixture=[fixture],
            historico=[
                event(51, "2029-12-20", home_id=101, away_id=303,
                      home_name="Casa Real", away_name="Rival A"),
                event(52, "2030-01-10", home_id=101, away_id=303,
                      home_name="Casa Real", away_name="Rival A"),
            ],
        )
        texto = contexto_espn(p, session=sessao)
        self.assertIn("01/01/2030 a 19/01/2030", texto)
        self.assertIn("10/01 (C) vs Rival A", texto)
        self.assertNotIn("20/12", texto)
        self.assertIn("limitada ao ano consultado", texto)
        self.assertEqual(sessao.calls[1][1]["dates"], "2030")
        self.assertEqual(len(sessao.calls), 2)

    def test_resultados_sem_final_ignorado(self):
        s = Sessao(historico=[event(99, "2030-10-10", finished=False)])
        texto = contexto_espn(snapshot(), session=s)
        self.assertIn("nenhum jogo oficial confirmado no intervalo", texto)
        self.assertIn("Confrontos diretos na janela: 0", texto)

    def test_comando_opcional_so_admin_sem_alterar_snapshot(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = 42
        bot.chat_id = 42
        bot.username = None
        hoje = datetime.now(TZ_PT)
        p = snapshot()
        p["data_jogo"] = hoje.strftime("%Y-%m-%d")
        p["timestamp_jogo"] = (hoje + timedelta(hours=3)).timestamp()
        p["criada_em"] = (hoje - timedelta(hours=1)).isoformat()
        bot.previsoes = SimpleNamespace(dados={"previsoes": [p]})
        antes = copy.deepcopy(bot.previsoes.dados)
        respostas = []
        bot.enviar_mensagem = lambda chat, texto: respostas.append((chat, texto))
        with patch("estudo_forma_espn.contexto_espn", return_value="FORM_EVIDENCE") as pedido:
            bot.processar_comando(42, "/estudo_jogo 1 forma", user_id=42)
            self.assertEqual(respostas[0], (42, "FORM_EVIDENCE"))
            self.assertEqual(pedido.call_count, 1)
            bot.processar_comando(43, "/estudo_jogo 1 forma", user_id=43)
            self.assertEqual(pedido.call_count, 1)
            bot.processar_comando(42, "/estudo_jogo 2 forma", user_id=42)
            self.assertEqual(pedido.call_count, 1)
        self.assertEqual(bot.previsoes.dados, antes)

    def test_lista_continua_offline_sem_api(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 42
        bot.username = None
        hoje = datetime.now(TZ_PT)
        p = snapshot()
        p["data_jogo"] = hoje.strftime("%Y-%m-%d")
        p["timestamp_jogo"] = (hoje + timedelta(hours=3)).timestamp()
        bot.previsoes = SimpleNamespace(dados={"previsoes": [p]})
        with patch("estudo_forma_espn.contexto_espn", side_effect=AssertionError("sem API")):
            texto = bot._executar_estudo_jogo("")
        self.assertIn("/estudo_jogo 1 forma", texto)


if __name__ == "__main__":
    unittest.main()
