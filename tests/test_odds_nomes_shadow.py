"""Provas offline: catálogo de nomes não pode alterar fixtures, odds ou modelos."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_nomes_shadow import diagnosticar_nomes


PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 16, 23, 40, tzinfo=PT)


def previsao(agora=AGORA):
    return {
        "data_jogo": agora.date().isoformat(),
        "modelo_versao": "V1.2", "ranking_modelo": 3,
        "estado": "pendente", "timestamp_jogo": (agora - timedelta(minutes=15)).timestamp(),
        "casa": "Ponte Preta", "fora": "Atlético Goianiense",
        "mercado": "Under 2.5 Golos", "odd_real": None,
        "odd_minima": 1.51,
    }


class FonteFake:
    provider = "oddspapi"
    configurada = True
    def __init__(self, participants=None):
        self.participants = participants if participants is not None else {
            "201": "Ponte Preta Campinas", "202": "Ponte Preta Sub-20",
            "203": "Ponte Preta Women", "300": "Atlético GO",
            "301": "Atlético Goianiense Sub-20", "400": "Clube Distinto",
        }
        self.calls = []

    def _get_papi(self, endpoint, parametros):
        self.calls.append((endpoint, dict(parametros)))
        if endpoint != "/participants":
            raise AssertionError("Sem /fixtures nem /odds")
        return copy.deepcopy(self.participants)

    def contexto_operacao(self, nome):
        from contextlib import nullcontext
        return nullcontext()


class NomesShadowTests(unittest.TestCase):
    def test_devolve_nomes_parciais_ids_sem_associar_ou_mutar_snapshot(self):
        dados = [previsao()]
        copia = copy.deepcopy(dados)
        fonte = FonteFake()
        guards = []
        def guarda(operacao, reserva):
            guards.append((operacao, reserva))
            return True
        texto = diagnosticar_nomes(dados, fonte, "3", guarda, agora=AGORA)
        self.assertEqual(guards, [("ODDS_AUTO", 25)])
        self.assertEqual(len(fonte.calls), 1)
        self.assertEqual(fonte.calls[0][0], "/participants")
        self.assertEqual(fonte.calls[0][1]["sportId"], 10)
        self.assertIn("Ponte Preta Campinas — ID 201", texto)
        self.assertIn("Ponte Preta Sub-20 — ID 202", texto)
        self.assertIn("Atlético GO — ID 300", texto)
        self.assertIn("PARCIAL", texto)
        self.assertIn("Sem /fixtures, /odds, VALUE", texto)
        self.assertEqual(dados, copia)

    def test_catalogo_sem_id_validado_ignora_valores_invalidos(self):
        fonte = FonteFake({
            "x": "Ponte Preta",
            "-3": "Ponte Preta Women",
            "12": "Ponte Preta Sub-20",
            "14": 123,
        })
        t = diagnosticar_nomes([previsao()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("Ponte Preta Sub-20 — ID 12", t)
        self.assertNotIn("— ID -3", t)
        self.assertNotIn("— ID x", t)

    def test_sem_quota_sem_chamada(self):
        fonte = FonteFake()
        t = diagnosticar_nomes([previsao()], fonte, "3", lambda *a: False, agora=AGORA)
        self.assertIn("reserva CLV", t)
        self.assertEqual(fonte.calls, [])

    def test_rejeita_ranking_e_tipo_invalido(self):
        fonte = FonteFake()
        for arg in ("0", "3 abrir", "", "9999"):
            self.assertIn("Formato", diagnosticar_nomes([previsao()], fonte, arg, lambda *a: True, agora=AGORA))
        self.assertEqual(fonte.calls, [])

    def test_sem_snapshot_unico_nunca_consulta_api(self):
        fonte = FonteFake()
        t = diagnosticar_nomes([previsao(), previsao()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("repetido", t)
        self.assertEqual(fonte.calls, [])

    def test_dia_historico_permite_so_catalogo_sem_odd(self):
        fonte = FonteFake()
        p = previsao()
        entrada = [p]
        antes = copy.deepcopy(entrada)
        futuro = AGORA + timedelta(days=1)
        t = diagnosticar_nomes(
            entrada, fonte, "2030-10-16 3", lambda *a: True, agora=futuro
        )
        self.assertIn("2030-10-16 | #3", t)
        self.assertIn("Ponte Preta Sub-20", t)
        self.assertEqual(entrada, antes)
        self.assertEqual([x[0] for x in fonte.calls], ["/participants"])
        self.assertIn("inexistente", diagnosticar_nomes(
            entrada, fonte, "3", lambda *a: True, agora=futuro
        ))
        self.assertEqual(len(fonte.calls), 1)

    def test_comando_historico_so_owner_e_cache_por_data(self):
        agora = datetime.now(PT)
        ontem = agora - timedelta(days=1)
        fonte = FonteFake()
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id, bot.chat_id, bot.username = 51, 51, None
        bot.previsoes = SimpleNamespace(dados={"previsoes": [previsao(ontem)]})
        bot.odds = fonte
        bot._quota_permite_captura = lambda *a: True
        bot._nomes_odds_cache = {}
        mensagens = []
        bot.enviar_mensagem = lambda chat, texto: mensagens.append((chat, texto))
        cmd = "/odds_nomes " + ontem.date().isoformat() + " 3"
        bot.processar_comando(13, cmd, user_id=13)
        bot.processar_comando(51, cmd, user_id=51)
        bot.processar_comando(51, cmd, user_id=51)
        self.assertEqual(len(mensagens), 2)
        self.assertIn(ontem.date().isoformat() + " | #3", mensagens[0][1])
        self.assertIn("cache", mensagens[1][1])
        self.assertEqual(len(fonte.calls), 1)

    def test_alerta_homonimos_e_escaloes_so_no_relatorio(self):
        dados = [previsao()]
        originais = copy.deepcopy(dados)
        fonte = FonteFake({
            "1969": "AA Ponte Preta SP",
            "210352": "AA Ponte Preta SP",
            "1133305": "Ponte Preta AL",
            "1276210": "Atletico Cg GO U20",
            "1386954": "Atletico Itumbiara GO",
        })
        texto = diagnosticar_nomes(dados, fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("Nome repetido com IDs distintos: AA Ponte Preta SP — 1969, 210352", texto)
        self.assertIn("candidato(s) Sub-20/U20", texto)
        self.assertEqual(texto.count("Nenhum nome canónico exato"), 2)
        self.assertIn("Atletico Itumbiara GO — ID 1386954", texto)
        self.assertEqual(dados, originais)
        self.assertEqual([call[0] for call in fonte.calls], ["/participants"])

    def test_aviso_homonimos_nao_aparece_com_ids_unicos(self):
        fonte = FonteFake({"1969": "Ponte Preta", "300": "Atletico GO"})
        texto = diagnosticar_nomes(
            [previsao()], fonte, "3", lambda *a: True, agora=AGORA
        )
        self.assertNotIn("Nome repetido com IDs distintos", texto)
        self.assertNotIn("candidato(s) Sub-20/U20", texto)
        self.assertNotIn("Nenhum nome canónico exato", texto)
        self.assertEqual(len(fonte.calls), 1)

    def test_so_owner_e_cache_na_mesma_sessao(self):
        agora = datetime.now(PT)
        fonte = FonteFake()
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id, bot.chat_id, bot.username = 51, 51, None
        bot.previsoes = SimpleNamespace(dados={"previsoes": [previsao(agora)]})
        bot.odds = fonte
        bot._quota_permite_captura = lambda *a: True
        bot._nomes_odds_cache = {}
        enviados = []
        bot.enviar_mensagem = lambda chat, texto: enviados.append((chat, texto))
        bot.processar_comando(13, "/odds_nomes 3", user_id=13)
        bot.processar_comando(51, "/odds_nomes 3", user_id=51)
        bot.processar_comando(51, "/odds_nomes 3", user_id=51)
        self.assertEqual(len(enviados), 2)
        self.assertIn("NOMES DA ODDS PAPI", enviados[0][1])
        self.assertIn("cache", enviados[1][1])
        self.assertEqual(len(fonte.calls), 1)


if __name__ == "__main__":
    unittest.main()
