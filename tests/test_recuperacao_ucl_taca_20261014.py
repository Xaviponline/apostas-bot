"""Regressões isoladas da cobertura histórica (14/10/2026).

Sem rede e sem mudanças em V1.2, SEL1, V1.3 ou snapshots.
As épocas e os eventos abaixo são fixtures sintéticas, NÃO resultados reais.
"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_espn_competicoes import EstatisticasESPNCompeticoes
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from main_enriquecido import EstatisticasESPNEnriquecidas


REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))


class SofaHistoricoFake:
    def __init__(self, tournament_id, total=24, year="26/27"):
        self.tournament_id = tournament_id
        self.total = total
        self.year = year
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        raiz = f"/unique-tournament/{self.tournament_id}"
        if caminho == f"{raiz}/seasons":
            return {"seasons": [{
                "id": 99000 + self.tournament_id, "year": self.year,
                "name": f"Fixture {self.year}",
            }]}
        if caminho == f"{raiz}/season/{99000 + self.tournament_id}/events/last/0":
            return {
                "events": [{
                    "id": 7000000 + i,
                    "startTimestamp": int(REF.timestamp()) - (i + 3) * 86400,
                    "status": {"code": 100, "type": "finished"},
                    "homeTeam": {"id": 1000 + i, "name": f"Casa {i}"},
                    "awayTeam": {"id": 2000 + i, "name": f"Fora {i}"},
                    "homeScore": {"normaltime": 2, "current": 2},
                    "awayScore": {"normaltime": 1, "current": 1},
                } for i in range(self.total)],
                "hasNextPage": False,
            }
        raise ValueError("Caminho SofaScore inesperado no fixture")


class RecuperacaoHistoricoTests(unittest.TestCase):
    def test_ids_e_fallback_direto_sem_escrever_na_espn(self):
        for codigo, torneo in (
            ("uefa.champions", 7),
            ("por.taca.portugal", 336),
        ):
            with self.subTest(codigo=codigo):
                class Probe(EstatisticasHibridasCompeticoes):
                    def _recolher_base_tolerante(self, *args, **kwargs):
                        raise AssertionError("ESPN não deve ser consultada")

                sofa = SofaHistoricoFake(torneo)
                stats = Probe(sofa_client=sofa)
                self.assertIn(codigo, stats.ESPN_HISTORICO_BLOQUEADO)
                self.assertEqual(stats.SOFA_TOURNAMENT_IDS[codigo], torneo)
                historico = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(historico), 24)
                diag = stats.diagnostico_base[codigo]
                self.assertEqual(diag["fonte"], "sofascore")
                self.assertEqual(diag["torneio_id"], torneo)
                self.assertEqual(diag["temporada_id"], 99000 + torneo)
                self.assertEqual(sofa.chamadas[0], f"/unique-tournament/{torneo}/seasons")

    def test_escassez_de_jogos_nao_e_promovida_a_historico_valido(self):
        for codigo, torneo in (("uefa.champions", 7), ("por.taca.portugal", 336)):
            with self.subTest(codigo=codigo):
                stats = EstatisticasHibridasCompeticoes(
                    sofa_client=SofaHistoricoFake(torneo, total=9)
                )
                with self.assertRaisesRegex(ValueError, "base insuficiente"):
                    stats._fetch_liga(codigo, REF)
                self.assertEqual(
                    stats.diagnostico_base[codigo]["fonte"], "sofascore_indisponivel"
                )

    def test_epoca_desconhecida_nao_gera_historico(self):
        stats = EstatisticasHibridasCompeticoes(
            sofa_client=SofaHistoricoFake(336, year="25/26")
        )
        with self.assertRaisesRegex(ValueError, "época 26/27 não encontrada"):
            stats._fetch_liga("por.taca.portugal", REF)

    def test_liga_regular_nao_e_encaminhada_para_sofa(self):
        class Probe(EstatisticasHibridasCompeticoes):
            def _consultar_intervalo(self, codigo, inicio, fim):
                return []

            def _sofa_get(self, caminho):
                raise AssertionError("Liga regular não pode usar fallback SofaScore")

        self.assertEqual(Probe()._fetch_liga("esp.1", REF), [])


class Http400RegressoesTests(unittest.TestCase):
    @staticmethod
    def _erro_400():
        resposta = requests.Response()
        resposta.status_code = 400
        return requests.HTTPError("segredo-nao-mostrar", response=resposta)

    def test_400_sem_sucesso_interrompe_ao_segundo_bloco(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__()
                self.chamadas = 0

            def _consultar_intervalo(self, *args):
                self.chamadas += 1
                raise Http400RegressoesTests._erro_400()

        stats = Probe()
        with self.assertRaises(requests.HTTPError):
            stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(stats.chamadas, 2)
        diag = stats.diagnostico_base["uefa.champions"]
        self.assertEqual(diag["blocos"], 2)
        self.assertTrue(diag["http_400_interrompido"])
        self.assertEqual(diag["motivos"], ["HTTP 400"])
        self.assertNotIn("segredo", str(diag))

    def test_400_apenas_num_bloco_nao_esconde_dados_reais(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__()
                self.chamadas = 0

            def _consultar_intervalo(self, *args):
                self.chamadas += 1
                if self.chamadas == 1:
                    raise Http400RegressoesTests._erro_400()
                return [{"id": i, "timestamp": float(i)} for i in range(24)]

            def _normalizar_eventos(self, eventos, codigo):
                return {e["id"]: e for e in eventos}

        stats = Probe()
        historico = stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(len(historico), 24)
        self.assertEqual(stats.chamadas, 2)
        self.assertFalse(stats.diagnostico_base["uefa.champions"]["http_400_interrompido"])

    def test_timeout_conserva_a_politica_de_retry(self):
        class Probe(EstatisticasESPNCompeticoes):
            def __init__(self):
                super().__init__()
                self.chamadas = 0

            def _consultar_intervalo(self, *args):
                self.chamadas += 1
                if self.chamadas == 1:
                    raise requests.Timeout("simulado")
                return [{"id": i, "timestamp": float(i)} for i in range(24)]

            def _normalizar_eventos(self, eventos, codigo):
                return {e["id"]: e for e in eventos}

        stats = Probe()
        self.assertEqual(len(stats._fetch_liga("uefa.champions", REF)), 24)
        self.assertEqual(stats.chamadas, 2)


class FaseGenericaTests(unittest.TestCase):
    @staticmethod
    def _evento(slug_liga=None):
        return {
            "id": "1234567",
            "date": "2026-10-14T20:00:00Z",
            "season": {"name": "Group Stage", "slug": "2026-27-group-stage"},
            "league": {"name": "Group Stage"},
            "competitions": [{
                "league": {"name": "Group Stage", "slug": slug_liga},
                "competitors": [
                    {"homeAway": "home", "team": {"id": "101", "displayName": "Casa"}},
                    {"homeAway": "away", "team": {"id": "202", "displayName": "Fora"}},
                ],
            }],
        }

    def test_group_stage_com_slug_liga_dos_campeoes(self):
        jogo = BuscadorJogosReais._normalizar_evento_espn(
            self._evento("uefa-champions-league")
        )
        self.assertEqual(jogo["liga"], "UEFA Champions League")
        self.assertEqual(EstatisticasESPNEnriquecidas.resolver_liga(jogo), "uefa.champions")

    def test_group_stage_com_slug_taca_de_portugal(self):
        jogo = BuscadorJogosReais._normalizar_evento_espn(
            self._evento("portuguese-taca-de-portugal")
        )
        self.assertEqual(jogo["liga"], "Portuguese Taca de Portugal")
        self.assertEqual(
            EstatisticasESPNEnriquecidas.resolver_liga(jogo), "por.taca.portugal"
        )

    def test_group_stage_sem_slug_identificavel_fica_sem_cobertura(self):
        jogo = BuscadorJogosReais._normalizar_evento_espn(
            self._evento("unknown-group-stage")
        )
        self.assertEqual(jogo["liga"], "Group Stage")
        self.assertIsNone(EstatisticasESPNEnriquecidas.resolver_liga(jogo))


if __name__ == "__main__":
    unittest.main()
