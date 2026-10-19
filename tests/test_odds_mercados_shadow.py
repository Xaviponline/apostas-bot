"""Testes offline do diagnóstico OWNER de metadados OddsPapi."""
import copy
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_mercados_shadow import diagnosticar_mercado


PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 10, 19, 10, 15, tzinfo=PT)


def previsao(agora=AGORA):
    return {
        "data_jogo": agora.date().isoformat(),
        "modelo_versao": "V1.2", "ranking_modelo": 1,
        "estado": "pendente",
        "timestamp_jogo": (agora + timedelta(hours=3)).timestamp(),
        "casa": "Jong FC Utrecht", "fora": "Roda JC Kerkrade",
        "mercado": "Under 3.5 Golos", "odd_real": None, "odd_minima": 1.51,
        "valor_estado": "sem_odd",
    }


class FonteFake:
    provider = "oddspapi"
    configurada = True

    def __init__(self, agora=AGORA, mercados=None, catalogo=None):
        self._eventos_cache = [{
            "id": "fixture-123",
            "casa": "Jong FC Utrecht", "fora": "Roda JC Kerkrade",
            "data": (agora + timedelta(hours=3)).isoformat(),
        }]
        self._catalogo_mercados = {} if catalogo is None else catalogo
        self.mercados = mercados if mercados is not None else [{
            "id": "106", "name": "Market 106", "handicap": None,
            "period": "", "odds": [{"seleção": "107", "odd": 1.77}],
        }]
        self.calls = []

    def eventos_hoje(self):
        self.calls.append("eventos")
        return self._eventos_cache

    def contexto_operacao(self, nome):
        return nullcontext()

    def odds_evento(self, fixture):
        self.calls.append(("odds", fixture))
        return {
            "id": fixture,
            "bookmaker_disponivel": True,
            "mercados": copy.deepcopy(self.mercados),
            "casa": "Jong FC Utrecht", "fora": "Roda JC Kerkrade",
        }

    def _get_papi(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint != "/markets":
            raise AssertionError("Endpoint imprevisto")
        return [{"marketId": 106, "marketName": "Over Under Full Time"}]

    def diagnostico_evento(self, fixture):
        return "odds_evento_indisponiveis"


class MercadosShadowTests(unittest.TestCase):
    def test_catalogo_vazio_mercados_ids_e_sondagem_nao_reparam_preco(self):
        dados = [previsao()]
        antes = copy.deepcopy(dados)
        fonte = FonteFake()
        guards = []
        def guarda(op, reserva):
            guards.append((op, reserva))
            return True
        texto = diagnosticar_mercado(dados, fonte, "1", guarda, agora=AGORA)
        self.assertIn("Catálogo /markets em memória: 0", texto)
        self.assertIn("Market 106", texto)
        self.assertIn("1 IDs presentes no payload", texto)
        self.assertIn("HIPÓTESE FORTE", texto)
        self.assertIn("mercado_nao_disponivel", texto)
        self.assertEqual([c[0] for c in fonte.calls], ["odds", "/markets"])
        self.assertEqual(len(guards), 3)
        self.assertEqual(dados, antes)
        self.assertEqual(fonte._catalogo_mercados, {})

    def test_mercado_nomeado_reconhecido_sem_mudar_odd_congelada(self):
        dados = [previsao()]
        antes = copy.deepcopy(dados)
        fonte = FonteFake(
            mercados=[{
                "id": "123", "name": "Over Under Full Time",
                "period": "fulltime", "handicap": 3.5,
                "odds": [{"seleção": "Under", "odd": 1.72}],
            }],
            catalogo={"123": {"name": "Over Under Full Time"}},
        )
        txt = diagnosticar_mercado(dados, fonte, "1", lambda *a: True, agora=AGORA)
        self.assertIn("Mercados compatíveis com a seleção: 1", txt)
        self.assertIn("preço identificado no payload", txt)
        self.assertNotIn("Sondagem /markets", txt)
        self.assertEqual(fonte.calls, [("odds", "fixture-123")])
        self.assertEqual(dados, antes)

    def test_sem_quota_sem_consultas(self):
        fonte = FonteFake()
        t = diagnosticar_mercado([previsao()], fonte, "1", lambda *a: False, agora=AGORA)
        self.assertIn("orçamento diário", t)
        self.assertEqual(fonte.calls, [])

    def test_ambiguidade_ou_hora_divergente_impede_odds(self):
        for caso in ("duplicado", "horario"):
            fonte = FonteFake()
            if caso == "duplicado":
                fonte._eventos_cache.append(dict(fonte._eventos_cache[0], id="fixture-outro"))
            else:
                fonte._eventos_cache[0]["data"] = (AGORA + timedelta(hours=6)).isoformat()
            t = diagnosticar_mercado([previsao()], fonte, "1", lambda *a: True, agora=AGORA)
            self.assertIn("consulta /odds", t)
            self.assertEqual(fonte.calls, [])

    def test_jogo_iniciado_e_ranking_invalido_nao_consultam(self):
        fonte = FonteFake()
        p = previsao()
        p["timestamp_jogo"] = (AGORA - timedelta(minutes=1)).timestamp()
        self.assertIn("pendentes", diagnosticar_mercado([p], fonte, "1", lambda *a: True, agora=AGORA))
        for arg in ("", "0", "21", "1 outra", "001", "-1"):
            self.assertIn("Formato", diagnosticar_mercado([previsao()], fonte, arg, lambda *a: True, agora=AGORA))
        self.assertEqual(fonte.calls, [])

    def test_sondagem_catalogo_suspensa_apos_consulta_por_reserva(self):
        fonte = FonteFake()
        chamadas = 0
        def guarda(*args):
            nonlocal chamadas
            chamadas += 1
            return chamadas <= 2
        t = diagnosticar_mercado([previsao()], fonte, "1", guarda, agora=AGORA)
        self.assertIn("não executada: reserva CLV", t)
        self.assertEqual(fonte.calls, [("odds", "fixture-123")])

    def test_comando_somente_owner_cache_mesmo_ranking(self):
        agora = datetime.now(PT)
        fonte = FonteFake(agora)
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id, bot.chat_id, bot.username = 51, 51, None
        bot.previsoes = SimpleNamespace(dados={"previsoes": [previsao(agora)]})
        bot.odds = fonte
        bot._quota_permite_captura = lambda *args: True
        mensagens = []
        bot.enviar_mensagem = lambda chat, texto: mensagens.append((chat, texto))
        bot.processar_comando(52, "/odds_mercados 1", user_id=52)
        self.assertEqual(mensagens, [])
        bot.processar_comando(51, "/odds_mercados 1", user_id=51)
        bot.processar_comando(51, "/odds_mercados 1", user_id=51)
        self.assertEqual(len(mensagens), 2)
        self.assertIn("MERCADOS ODDS PAPI", mensagens[0][1])
        self.assertIn("zero pedidos adicionais", mensagens[1][1])
        self.assertEqual([x[0] for x in fonte.calls], ["odds", "/markets"])


if __name__ == "__main__":
    unittest.main()
