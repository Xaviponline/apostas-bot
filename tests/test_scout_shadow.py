"""Testes totalmente offline da carteira prospetiva SCOUT SHADOW."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from main_competicoes import BotPremiumDiarioCompeticoes
from scout_shadow import (
    LIGAS, MAX_LIGAS_DIA, MIN_LIQUIDADAS, ScoutShadow, _possiveis,
    _match, _registo, _wilson, _liga,
)

AGORA = datetime(2026, 10, 24, 9, 5, tzinfo=timezone.utc)
START = "2026-10-24T19:30:00Z"
TS = datetime(2026, 10, 24, 19, 30, tzinfo=timezone.utc).timestamp()
SPORT = "soccer_portugal_primeira_liga"


def snap(**updates):
    p = {
        "chave": "one|Over 2.5 Golos",
        "event_id": 12345, "timestamp_jogo": TS,
        "data_jogo": "2026-10-24", "casa": "Gil Vicente",
        "fora": "FC Porto", "liga": "Portuguese Primeira Liga",
        "mercado": "Over 2.5 Golos", "ranking_modelo": 2,
        "estado": "pendente", "probabilidade": 0.68,
        "qualidade": 83, "odd_minima": 1.56,
        "snapshot_hash": "EXEMPLO_SELO",
    }
    p.update(updates)
    return p


def evento():
    return {
        "id": "aaaaaaaaaaaaaaaa", "home_team": "Gil Vicente",
        "away_team": "FC Porto", "commence_time": START,
        "bookmakers": [
            {
                "key": k,
                "markets": [{
                    "key": "totals", "last_update": "2026-10-24T09:02:00Z",
                    "outcomes": [
                        {"name": "Over", "point": 2.5, "price": price},
                        {"name": "Under", "point": 2.5, "price": 1.93},
                        {"name": "Over", "point": 3.5, "price": 9.99},
                    ]
                }],
            }
            for k, price in (("a", 1.8), ("b", 1.84), ("c", 1.88))
        ],
    }


def fonte_com_dados():
    calls = []
    def get(sess, path, params):
        calls.append((path, dict(params)))
        if path == "/sports/":
            return [{"key": SPORT, "active": True}], None, {"x-requests-remaining": "496"}
        if path == f"/sports/{SPORT}/odds":
            return [evento()], None, {
                "x-requests-last": "2", "x-requests-remaining": "492",
            }
        raise AssertionError(path)
    return get, calls


class ScoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "scout_shadow.json"
        self.scout = ScoutShadow(self.path, session=object())

    def tearDown(self):
        self.tmp.cleanup()

    def test_top5_filtra_e_nao_inventa_jogos(self):
        ps = [snap(), snap(chave="bad", ranking_modelo=6),
              snap(chave="bad2", mercado="Ambas Marcam"),
              snap(chave="bad3", probabilidade=.60),
              snap(chave="bad4", data_jogo="2026-10-25")]
        candidatos, motivos = _possiveis(ps, AGORA)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(motivos["fora_top5"], 1)
        self.assertEqual(motivos["mercado_nao_coberto"], 1)
        self.assertEqual(motivos["filtro_exigente"], 1)

    def test_sem_snapshots_nao_faz_rede_nem_cria_ledger(self):
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            did, message = self.scout.executar([], agora=AGORA, chave="SEGREDO")
        self.assertFalse(did)
        self.assertIn("zero pedidos API", message)
        self.assertFalse(self.path.exists())

    def test_com_20_previsoes_sem_candidatos_guarda_estado_e_zero_http(self):
        # Com analise V1.2 concluida, nao confundir sem candidatos com falha.
        amostra = [
            snap(chave=f"modelo-{i}", ranking_modelo=i, mercado="Ambas Marcam")
            for i in range(1, 21)
        ]
        original = copy.deepcopy(amostra)
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            fez, texto = self.scout.executar(amostra, agora=AGORA, chave="SEGREDO")
        self.assertTrue(fez)
        self.assertIn("20 previsoes de hoje analisadas", texto)
        self.assertIn("mercado_nao_coberto=5", texto)
        self.assertIn("fora_top5=15", texto)
        self.assertEqual(amostra, original)
        dados = json.loads(self.path.read_text(encoding="utf-8"))
        entrada = dados["dias"]["2026-10-24"]
        self.assertEqual(entrada["estado"], "sem_candidatos")
        self.assertEqual(entrada["creditos_estimados_reservados"], 0)
        self.assertEqual(entrada["snapshots_do_dia"], 20)
        self.assertEqual(entrada["selecoes"], [])
        self.assertIn("sem_candidatos", self.scout.hoje(agora=AGORA))

    def test_dia_sem_candidatos_nao_repete_nem_apos_restart(self):
        amostra = [snap(mercado="Ambas Marcam")]
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            self.scout.executar(amostra, agora=AGORA, chave="SEGREDO")
            repetido = ScoutShadow(self.path, session=object())
            fez, resposta = repetido.executar(amostra, agora=AGORA, chave="SEGREDO")
        self.assertFalse(fez)
        self.assertIn("ja registado", resposta)
        self.assertIn("sem_candidatos", resposta)

    def test_sem_previsoes_antes_analise_nao_fecha_dia(self):
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            primeiro, resposta = self.scout.executar([], agora=AGORA, chave="SEGREDO")
            segundo, resposta2 = self.scout.executar(
                [snap(mercado="Ambas Marcam")], agora=AGORA, chave="SEGREDO"
            )
        self.assertFalse(primeiro)
        self.assertIn("Aguardar analise automatica", resposta)
        self.assertTrue(segundo)
        self.assertIn("sem_candidatos", resposta2)
        self.assertEqual(len(json.loads(self.path.read_text())["dias"]), 1)

    def test_aceita_previsao_e_regista_auditavel(self):
        get, calls = fonte_com_dados()
        original = snap()
        copia = copy.deepcopy(original)
        with patch("scout_shadow._get", side_effect=get):
            did, msg = self.scout.executar([original], agora=AGORA, chave="SEGREDO")
        self.assertTrue(did)
        self.assertIn("Candidatas apos filtros de odds: 1", msg)
        self.assertIn("Modelo 68,0%", msg)
        self.assertIn("Ref, 1,84", msg)
        self.assertIn("Min, modelo 1,56", msg)
        self.assertEqual(original, copia)
        ledger = json.loads(self.path.read_text())
        self.assertEqual(ledger["dias"]["2026-10-24"]["estado"], "concluido")
        self.assertEqual(len(ledger["dias"]["2026-10-24"]["selecoes"]), 1)
        self.assertEqual(ledger["dias"]["2026-10-24"]["selecoes"][0]["bookmakers"], 3)
        self.assertNotIn("SEGREDO", self.path.read_text())
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1]["regions"], "eu")
        self.assertEqual(calls[1][1]["markets"], "h2h,totals")

    def test_repetir_mesmo_dia_zero_rede(self):
        get, _ = fonte_com_dados()
        with patch("scout_shadow._get", side_effect=get):
            self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        with patch("scout_shadow._get", side_effect=AssertionError("repeticao")):
            did, msg = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertFalse(did)
        self.assertIn("ja registado", msg)

    def test_chave_ausente_sem_rede(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("scout_shadow._get", side_effect=AssertionError("rede")):
                did, msg = self.scout.executar([snap()], agora=AGORA)
        self.assertFalse(did)
        self.assertIn("indisponivel", msg)

    def test_evento_ambiguo_ou_hora_errada_rejeitado(self):
        e = evento()
        self.assertIsNone(_match([e, e], snap(), AGORA))
        e["commence_time"] = "2026-10-24T18:30:00Z"
        self.assertIsNone(_match([e], snap(), AGORA))
        self.assertIsNone(_match([e], snap(fora="Benfica"), AGORA))

    def test_rejeita_odd_stale_e_linhas_erradas(self):
        e = evento()
        for b in e["bookmakers"]:
            b["markets"][0]["last_update"] = "2026-10-20T09:00:00Z"
        self.assertEqual(_registo(snap(), e, SPORT, AGORA)[1], "casas_insuficientes")
        e = evento()
        for b in e["bookmakers"]:
            b["markets"][0]["outcomes"] = [
                {"name": "Over", "point": 3.5, "price": 2.3}
            ]
        self.assertEqual(_registo(snap(), e, SPORT, AGORA)[1], "casas_insuficientes")

    def test_rejeita_odds_sem_edge_pre_criterio(self):
        e = evento()
        self.assertEqual(_registo(snap(odd_minima=2.0), e, SPORT, AGORA)[1],
                         "sem_margem_teorica")
        self.assertEqual(_registo(snap(probabilidade=.63, odd_minima=1.51),
                                  e, SPORT, AGORA)[1], None)
        for b in e["bookmakers"]:
            b["markets"][0]["outcomes"][0]["price"] = 1.30
        self.assertEqual(_registo(snap(), e, SPORT, AGORA)[1],
                         "odd_baixa_ou_divergente")

    def test_nao_regista_mesmo_jogo_com_casas_contraditorias(self):
        e = evento()
        e["bookmakers"][2]["markets"][0]["outcomes"][0]["price"] = 15.0
        self.assertEqual(_registo(snap(), e, SPORT, AGORA)[1],
                         "odd_baixa_ou_divergente")

    def test_liga_nao_ativa_nao_consumir_odds(self):
        calls = []
        def get(sess, path, params):
            calls.append(path)
            return [{"key": SPORT, "active": False}], None, {"x-requests-remaining": "496"}
        with patch("scout_shadow._get", side_effect=get):
            did, msg = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertTrue(did)
        self.assertEqual(calls, ["/sports/"])
        self.assertIn("liga_sem_odds_api=1", msg)

    def test_quota_inicio_baixa_protege_sem_consultas_pagas(self):
        calls = []
        def get(sess, path, params):
            calls.append(path)
            return [{"key": SPORT, "active": True}], None, {
                "x-requests-remaining": "99"
            }
        with patch("scout_shadow._get", side_effect=get):
            did, msg = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertTrue(did)
        self.assertEqual(calls, ["/sports/"])
        self.assertIn("reserva_quota", msg)

    def test_sem_header_quota_falha_fechada(self):
        calls = []
        def get(sess, path, params):
            calls.append(path)
            return [{"key": SPORT, "active": True}], None, None
        with patch("scout_shadow._get", side_effect=get):
            did, msg = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertTrue(did)
        self.assertEqual(calls, ["/sports/"])
        self.assertIn("quota_nao_confirmada", msg)

    def test_http_erro_termina_mas_nao_repete(self):
        calls = []
        def get(sess, path, params):
            calls.append(path)
            if path == "/sports/":
                return [{"key": SPORT, "active": True}], None, {"x-requests-remaining": "496"}
            return None, "HTTP 401", None
        with patch("scout_shadow._get", side_effect=get):
            did, msg = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertTrue(did)
        self.assertIn("fonte_indisponivel=1", msg)
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            did, _ = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertFalse(did)

    def test_carteira_corrompida_falha_fechada(self):
        self.path.write_text("{invalido", encoding="utf-8")
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            with self.assertRaises(RuntimeError):
                self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertEqual(self.path.read_text(), "{invalido")

    def test_limite_creditos_mensal_impede_consulta(self):
        dados = {"versao": 1, "dias": {
            "2026-10-01": {"creditos_estimados_reservados": 120}
        }}
        self.path.write_text(json.dumps(dados))
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            did, msg = self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        self.assertFalse(did)
        self.assertIn("Limite local mensal", msg)

    def test_performance_so_resultado_existente_e_mesmo_hash(self):
        get, _ = fonte_com_dados()
        with patch("scout_shadow._get", side_effect=get):
            self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        perf = self.scout.desempenho([snap(resultado_binario=1)])
        self.assertIn("Liquidados: 1", perf)
        self.assertIn("Acerto: 100,0%", perf)
        self.assertIn("Brier", perf)
        self.assertIn("ROI SIMULADO", perf)
        self.assertIn("Amostra insuficiente", perf)
        self.assertIn("Baseline V1,2 Top5", perf)
        self.assertIn("Por mercado", perf)
        perf = self.scout.desempenho([snap(resultado_binario=1, snapshot_hash="ALTERADO")])
        self.assertIn("Identidade invalida: 1", perf)
        self.assertNotIn("ROI SIMULADO", perf)

    def test_performance_sem_lucro_real_antes_de_liquidar(self):
        get, _ = fonte_com_dados()
        with patch("scout_shadow._get", side_effect=get):
            self.scout.executar([snap()], agora=AGORA, chave="SEGREDO")
        perf = self.scout.desempenho([snap()])
        self.assertIn("Pendentes: 1", perf)
        self.assertNotIn("ROI SIMULADO", perf)

    def test_wilson_intervalo_nao_usa_so_hit_rate(self):
        lo, hi = _wilson(10, 10)
        self.assertLess(lo, 1.0)
        self.assertAlmostEqual(hi, 1.0, places=12)
        self.assertIsNone(_wilson(0, 0))

    def test_comandos_owner_hoje_performance_e_executar(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        bot.username = None
        bot.previsoes = type("Store", (), {"dados": {"previsoes": [snap()]}})()
        bot._scout_shadow = self.scout
        enviados = []
        bot.enviar_mensagem = lambda c, msg: enviados.append(msg)
        with patch("scout_shadow.datetime") as mock_dt:
            mock_dt.now.return_value = AGORA
            with patch("scout_shadow._get", side_effect=AssertionError("sem API")):
                bot.processar_comando(52, "/scout_agora", user_id=52)
                bot.processar_comando(52, "/scout_hoje", user_id=52)
                bot.processar_comando(51, "/scout_hoje", user_id=51)
                bot.processar_comando(51, "/scout_performance", user_id=51)
        self.assertEqual(len(enviados), 2)
        self.assertIn("SCOUT SHADOW", enviados[0])
        self.assertIn("Ainda nao ha candidatas", enviados[1])

    def test_auto_optin_desligado_zero_rede(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 51
        with patch.dict("os.environ", {"SCOUT_SHADOW_AUTO": "0"}):
            with patch("scout_shadow._get", side_effect=AssertionError("API")):
                bot._scout_auto_se_devido()
        self.assertFalse(self.path.exists())

    def test_league_one_two_inglesas_suportadas_por_chave_exata(self):
        casos = {
            "English League One": "soccer_england_league1",
            "EFL League One": "soccer_england_league1",
            "English League Two": "soccer_england_league2",
            "EFL League Two": "soccer_england_league2",
        }
        for nome, codigo in casos.items():
            with self.subTest(liga=nome):
                self.assertEqual(_liga(snap(liga=nome)), codigo)
        # Nunca supor que uma League One sem país é inglesa.
        for ambigua in ("League One", "Scottish League One",
                         "League Two", "Scottish League Two", "Turkish Super Lig"):
            with self.subTest(liga_ambigua=ambigua):
                self.assertIsNone(_liga(snap(liga=ambigua)))

    def test_hoje_top5_league_one_substitui_so_bloqueio_mapeamento(self):
        originais = [
            snap(chave="4", ranking_modelo=4, liga="English League One",
                 casa="AFC Wimbledon", fora="Wycombe Wanderers",
                 mercado="Under 2.5 Golos"),
            snap(chave="5", ranking_modelo=5, liga="English League One",
                 casa="Oxford United", fora="Bradford City",
                 mercado="Under 2.5 Golos"),
        ]
        antes = copy.deepcopy(originais)
        candidatos, motivos = _possiveis(originais, AGORA)
        self.assertEqual(len(candidatos), 2)
        self.assertEqual(motivos["liga_sem_mapeamento"], 0)
        self.assertTrue(all(c[0] == "soccer_england_league1" for c in candidatos))
        self.assertEqual(originais, antes)

    def test_liga_mapeada_mas_ausente_catalogo_zero_odds_pagas(self):
        target = snap(chave="4", ranking_modelo=4, liga="English League One")
        calls = []
        def get(sess, path, params):
            calls.append(path)
            if path == "/sports/":
                return [{"key": "soccer_epl", "active": True}], None, {
                    "x-requests-remaining": "496"}
            raise AssertionError("Nunca pedir odds para liga indisponivel")
        with patch("scout_shadow._get", side_effect=get):
            feito, mensagem = self.scout.executar(
                [target], agora=AGORA, chave="SEGREDO")
        self.assertTrue(feito)
        self.assertEqual(calls, ["/sports/"])
        self.assertIn("liga_sem_odds_api=1", mensagem)

    def test_dia_guardado_sem_candidatos_nao_reabrir_apos_mapeamento(self):
        self.path.write_text(json.dumps({"versao":1, "dias":{
            "2026-10-24": {
                "estado":"sem_candidatos", "creditos_estimados_reservados":0,
                "ligas":[], "candidatos_modelo":0, "selecoes":[]
            }
        }}),encoding="utf-8")
        with patch("scout_shadow._get", side_effect=AssertionError("rede")):
            feito, txt = self.scout.executar(
                [snap(liga="English League One", ranking_modelo=4)],
                agora=AGORA, chave="SEGREDO")
        self.assertFalse(feito)
        self.assertIn("ja registado", txt)
        self.assertIn("sem_candidatos", txt)

    def test_map_portugal_e_teto_duas_ligas(self):
        self.assertEqual(LIGAS["portuguese primeira liga"], SPORT)
        self.assertEqual(MAX_LIGAS_DIA, 2)
        self.assertGreaterEqual(MIN_LIQUIDADAS, 40)


if __name__ == "__main__":
    unittest.main()
