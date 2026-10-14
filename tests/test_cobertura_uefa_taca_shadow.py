"""Testes SHADOW - cobertura de UEFA/Taca sem rede, odds ou snapshots."""
from datetime import datetime, timedelta
from unittest import TestCase
from zoneinfo import ZoneInfo

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from estatisticas_espn import EstatisticasESPN

REF = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


def evento_espn(ident, data="2026-10-02T20:00:00Z", terminado=True):
    return {
        "id": str(ident), "date": data,
        "status": {"type": {"state": "post" if terminado else "pre"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"id": "901", "displayName": "Casa"}, "score": "2"},
            {"homeAway": "away", "team": {"id": "902", "displayName": "Fora"}, "score": "1"},
        ]}],
    }


class Resposta:
    def __init__(self, dados, status=200):
        self._dados = dados
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("ESPN HTTP nao disponivel")

    def json(self):
        return self._dados


class EspnMensalFake:
    def __init__(self, por_mes=None, status=200):
        self.por_mes = por_mes or {}
        self.status = status
        self.pedidos = []

    def get(self, url, params=None, timeout=None, **kwargs):
        self.pedidos.append((url, dict(params or {})))
        return Resposta({"events": self.por_mes.get((params or {}).get("dates"), [])}, self.status)


class SofaVerificadoFake:
    def __init__(self, total=24, trocados=0, epoca="26/27"):
        self.total = total
        self.trocados = trocados
        self.epoca = epoca
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        for unique_id, season_id in [(7, 96518), (336, 98001)]:
            if caminho == f"/unique-tournament/{unique_id}/seasons":
                return {"seasons": [{"id": season_id, "year": self.epoca}]}
            if caminho == f"/unique-tournament/{unique_id}/season/{season_id}/events/last/0":
                return {"events": [
                    {
                        "id": unique_id * 100000 + i,
                        "startTimestamp": int((REF - timedelta(days=i+1)).timestamp()),
                        "status": {"code": 100, "type": "finished"},
                        "tournament": {"uniqueTournament": {
                            "id": unique_id if i >= self.trocados else 999,
                        }},
                        "homeTeam": {"id": 101+i, "name": "Casa"},
                        "awayTeam": {"id": 201+i, "name": "Fora"},
                        "homeScore": {"normaltime": 2}, "awayScore": {"normaltime": 1},
                    } for i in range(self.total)
                ], "hasNextPage": False}
        raise ValueError("Sofa indisponivel")


class HistoricoShadowTests(TestCase):
    def test_espn_mensal_cobre_ambas_sem_ranges_ou_sofascore(self):
        jogos = [evento_espn(i) for i in range(30)]
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                session = EspnMensalFake({"202610": jogos})
                sofa = SofaVerificadoFake()
                stats = EstatisticasHibridasCompeticoes(session=session, sofa_client=sofa)
                base = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(base), 30)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "espn_mensal")
                self.assertEqual(stats.diagnostico_base[codigo]["meses"], 1)
                self.assertEqual(len(session.pedidos), 1)
                self.assertEqual(session.pedidos[0][1], {"dates": "202610", "limit": 500})
                self.assertEqual(sofa.chamadas, [])
                self.assertTrue(all(x["liga_codigo"] == codigo for x in base))

    def test_filtro_temporal_ignora_jogos_futuros_e_ao_vivo(self):
        validos = [evento_espn(i) for i in range(8)]
        futuros = [evento_espn(i+100, "2026-10-17T20:00:00Z") for i in range(8)]
        por_iniciar = [evento_espn(i+200, "2026-10-03T20:00:00Z", terminado=False) for i in range(8)]
        setembro = [evento_espn(i+300, "2026-09-18T20:00:00Z") for i in range(18)]
        session = EspnMensalFake({"202610":validos+futuros+por_iniciar, "202609":setembro})
        stats = EstatisticasHibridasCompeticoes(session=session, sofa_client=SofaVerificadoFake())
        base = stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(len(base), 26)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["meses"], 2)
        self.assertTrue(all(x["timestamp"] < REF.timestamp() for x in base))

    def test_espn_cache_idempotente_sem_consultas_novas(self):
        session = EspnMensalFake({"202610": [evento_espn(i) for i in range(24)]})
        stats = EstatisticasHibridasCompeticoes(session=session, sofa_client=SofaVerificadoFake())
        base1 = stats._fetch_liga("uefa.champions", REF)
        base2 = stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(base1, base2)
        self.assertEqual(len(session.pedidos), 1)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["fonte"], "cache_espn_mensal")

    def test_espn_mensal_com_zero_jogos_nao_cria_base_falsa(self):
        stats = EstatisticasHibridasCompeticoes(
            session=EspnMensalFake(), sofa_client=SofaVerificadoFake(total=9),
        )
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["fonte"],
                         "espn_mensal_e_sofa_indisponiveis")

    def test_fallback_sofascore_so_se_espn_falhar(self):
        for codigo, uniq in [("uefa.champions", 7), ("por.taca.portugal", 336)]:
            with self.subTest(codigo=codigo):
                sofa = SofaVerificadoFake()
                stats = EstatisticasHibridasCompeticoes(
                    session=EspnMensalFake(status=400), sofa_client=sofa,
                )
                base = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(base), 24)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore")
                self.assertIn(f"/unique-tournament/{uniq}/seasons", sofa.chamadas)

    def test_sofa_rejeita_eventos_de_outro_torneio(self):
        stats = EstatisticasHibridasCompeticoes(
            session=EspnMensalFake(status=400),
            sofa_client=SofaVerificadoFake(total=24, trocados=20),
        )
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["fonte"],
                         "espn_mensal_e_sofa_indisponiveis")

    def test_sofa_rejeita_epoca_errada(self):
        stats = EstatisticasHibridasCompeticoes(
            session=EspnMensalFake(status=400),
            sofa_client=SofaVerificadoFake(epoca="25/26"),
        )
        with self.assertRaises(ValueError):
            stats._fetch_liga("por.taca.portugal", REF)

    def test_espn_mensal_rejeita_resposta_possivelmente_truncada(self):
        session = EspnMensalFake({"202610": [evento_espn(i) for i in range(500)]})
        stats = EstatisticasHibridasCompeticoes(
            session=session, sofa_client=SofaVerificadoFake(total=9),
        )
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["fonte"],
                         "espn_mensal_e_sofa_indisponiveis")

    def test_espn_mensal_nao_mexe_em_outras_ligas(self):
        self.assertNotIn("eng.2", EstatisticasHibridasCompeticoes.ESPN_HISTORICO_MENSAL)
        self.assertNotIn("arg.1", EstatisticasHibridasCompeticoes.ESPN_HISTORICO_MENSAL)


class NormalizacaoGroupStageShadowTests(TestCase):
    @staticmethod
    def evento(league=None, competicao_league=None, season_slug="group-stage"):
        return {
            "id": "401999123",
            "date": "2026-10-14T20:00:00Z",
            "league": league or {"name": "Group Stage"},
            "season": {"name": "Group Stage", "slug": season_slug},
            "status": {"type": {"state": "pre"}},
            "competitions": [{
                "league": competicao_league or {"name": "Group Stage"},
                "competitors": [
                    {"homeAway": "home", "team": {"id": "4", "displayName": "Casa"}},
                    {"homeAway": "away", "team": {"id": "5", "displayName": "Fora"}},
                ],
            }],
        }

    def test_slug_inequivoco_league_assegura_champions(self):
        jogo = BuscadorJogosReais._normalizar_evento_espn(
            self.evento(league={"name": "Group Stage", "slug": "uefa-champions-league"}))
        self.assertEqual(jogo["liga"], "UEFA Champions League")
        self.assertEqual(EstatisticasESPN.resolver_liga(jogo), "uefa.champions")

    def test_slug_da_competicao_identifica_taca(self):
        jogo = BuscadorJogosReais._normalizar_evento_espn(
            self.evento(competicao_league={"name": "Group Stage", "slug": "portuguese-taca-de-portugal"}))
        self.assertEqual(jogo["liga"], "Portuguese Taca de Portugal")

    def test_group_stage_ambiguo_continua_fora(self):
        jogo = BuscadorJogosReais._normalizar_evento_espn(self.evento())
        self.assertEqual(jogo["liga"], "Group Stage")
        self.assertIsNone(EstatisticasESPN.resolver_liga(jogo))
