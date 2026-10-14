"""Testes SHADOW de cobertura historica UEFA/Taca e nomes de fases genericos.

Sem chamadas live, sem OddsPapi, sem criar snapshots e sem alterar a V1.3.
O objetivo e garantir identidade, cobertura tecnica e falha fechada.
"""
from datetime import datetime, timedelta
from unittest import TestCase
from zoneinfo import ZoneInfo

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from estatisticas_espn import EstatisticasESPN

REF = datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


class SofaVerificadoFake:
    def __init__(self, total=24, trocados=0, epoca="26/27"):
        self.total = total
        self.trocados = trocados
        self.epoca = epoca
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        for codigo, unique_id, season_id in [
            ("uefa.champions", 7, 96518),
            ("por.taca.portugal", 336, 98001),
        ]:
            if caminho == f"/unique-tournament/{unique_id}/seasons":
                return {"seasons": [{
                    "id": season_id, "name": codigo + " " + self.epoca,
                    "year": self.epoca,
                }]}
            if caminho == f"/unique-tournament/{unique_id}/season/{season_id}/events/last/0":
                eventos = []
                for i in range(self.total):
                    evento = {
                        "id": unique_id * 100000 + i,
                        "startTimestamp": int((REF - timedelta(days=1 + i)).timestamp()),
                        "status": {"code": 100, "type": "finished"},
                        "tournament": {"uniqueTournament": {
                            "id": unique_id if i >= self.trocados else 999,
                        }},
                        "homeTeam": {"id": 10000 + i, "name": "Casa"},
                        "awayTeam": {"id": 20000 + i, "name": "Fora"},
                        "homeScore": {"normaltime": 2, "current": 3},
                        "awayScore": {"normaltime": 1, "current": 1},
                    }
                    eventos.append(evento)
                return {"events": eventos, "hasNextPage": False}
        raise AssertionError("API inesperada: " + caminho)


class HibridoShadowProbe(EstatisticasHibridasCompeticoes):
    def _recolher_base_tolerante(self, *args, **kwargs):
        raise AssertionError("Nao voltar a percorrer 31 blocos HTTP 400 da ESPN")

    def _consultar_intervalo(self, *args, **kwargs):
        raise AssertionError("Nao consultar ESPN com esta competicao bloqueada")


class HistoricoUefaTacaShadowTests(TestCase):
    def test_ids_e_rotas_verificados_para_ambas_provas(self):
        for codigo, unique_id in [
            ("uefa.champions", 7), ("por.taca.portugal", 336)
        ]:
            with self.subTest(codigo=codigo):
                sofa = SofaVerificadoFake()
                stats = HibridoShadowProbe(sofa_client=sofa)
                self.assertIn(codigo, stats.ESPN_HISTORICO_BLOQUEADO)
                self.assertEqual(stats.SOFA_TOURNAMENT_IDS[codigo], unique_id)
                base = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(base), 24)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore")
                self.assertIn(f"/unique-tournament/{unique_id}/seasons", sofa.chamadas)
                self.assertTrue(all(x["liga_codigo"] == codigo for x in base))
                self.assertTrue(all(x["golos_casa"] == 2 for x in base))
                self.assertTrue(all(x["timestamp"] < REF.timestamp() for x in base))

    def test_descarta_eventos_que_pertencem_a_outra_prova(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                sofa = SofaVerificadoFake(total=24, trocados=20)
                stats = HibridoShadowProbe(sofa_client=sofa)
                with self.assertRaises(ValueError):
                    stats._fetch_liga(codigo, REF)
                diag = stats.diagnostico_base[codigo]
                self.assertEqual(diag["fonte"], "sofascore_indisponivel")
                self.assertIn("4/10", diag["motivo"])

    def test_historico_aceita_so_amostra_suficiente_da_competicao(self):
        sofa = SofaVerificadoFake(total=9)
        stats = HibridoShadowProbe(sofa_client=sofa)
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.champions", REF)
        self.assertIn("base insuficiente", stats.diagnostico_base["uefa.champions"]["motivo"])

    def test_epoca_errada_nao_e_escolhida(self):
        sofa = SofaVerificadoFake(epoca="25/26")
        stats = HibridoShadowProbe(sofa_client=sofa)
        with self.assertRaises(ValueError):
            stats._fetch_liga("por.taca.portugal", REF)
        self.assertEqual(len(sofa.chamadas), 1)

    def test_provas_regulares_ficam_fora_da_nova_via(self):
        self.assertNotIn("eng.2", HibridoShadowProbe.ESPN_HISTORICO_BLOQUEADO)
        self.assertNotIn("arg.1", HibridoShadowProbe.ESPN_HISTORICO_BLOQUEADO)


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
        evento = self.evento(league={
            "name": "Group Stage", "slug": "uefa-champions-league"
        })
        jogo = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(jogo["liga"], "UEFA Champions League")
        self.assertEqual(EstatisticasESPN.resolver_liga(jogo), "uefa.champions")

    def test_slug_da_competicao_tambem_identifica_prova(self):
        evento = self.evento(competicao_league={
            "name": "Group Stage", "slug": "portuguese-taca-de-portugal"
        })
        jogo = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(jogo["liga"], "Portuguese Taca de Portugal")

    def test_group_stage_sem_slug_claro_nao_e_inventada(self):
        evento = self.evento()
        jogo = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(jogo["liga"], "Group Stage")
        self.assertIsNone(EstatisticasESPN.resolver_liga(jogo))
