"""Testes de cobertura historica SHADOW, sem alterar modelo ou producao."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from main_enriquecido import EstatisticasESPNEnriquecidas


REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))


class SofaHistoricoFake:
    def __init__(self, total=24, temporada="26/27", erro_pagina=False):
        self.total = total
        self.temporada = temporada
        self.erro_pagina = erro_pagina
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        if caminho.endswith("/seasons"):
            tid = int(caminho.split("/")[2])
            if tid not in (7, 336):
                raise AssertionError("Fonte ou torneio inesperado")
            return {
                "seasons": [{
                    "id": 96518 if tid == 7 else 90123,
                    "name": f"{'UEFA Champions League' if tid == 7 else 'Taça de Portugal'} {self.temporada}",
                    "year": self.temporada,
                }]
            }

        tid = int(caminho.split("/")[2])
        season = 96518 if tid == 7 else 90123
        esperado = f"/unique-tournament/{tid}/season/{season}/events/last/0"
        if caminho != esperado:
            raise AssertionError(f"Rota inesperada: {caminho}")
        if self.erro_pagina:
            raise ValueError("Pagina SofaScore indisponivel")

        base = datetime(2026, 9, 20, tzinfo=timezone.utc).timestamp()
        eventos = []
        for i in range(self.total):
            eventos.append({
                "id": (100000 if tid == 7 else 200000) + i,
                "startTimestamp": base - i * 86400,
                "status": {"code": 100, "type": "finished"},
                "homeTeam": {"id": 100 + i, "name": f"Casa {i}"},
                "awayTeam": {"id": 200 + i, "name": f"Fora {i}"},
                "homeScore": {"normaltime": 2, "current": 3},
                "awayScore": {"normaltime": 1, "current": 2},
            })
        return {"events": eventos, "hasNextPage": False}


class CoberturaHistoricoShadowTests(unittest.TestCase):
    def test_ids_e_atalho_fixo_evitam_31_blocos_400(self):
        self.assertEqual(EstatisticasHibridasCompeticoes.SOFA_TOURNAMENT_IDS["uefa.champions"], 7)
        self.assertEqual(EstatisticasHibridasCompeticoes.SOFA_TOURNAMENT_IDS["por.taca.portugal"], 336)
        self.assertIn("uefa.champions", EstatisticasHibridasCompeticoes.ESPN_HISTORICO_BLOQUEADO)
        self.assertIn("por.taca.portugal", EstatisticasHibridasCompeticoes.ESPN_HISTORICO_BLOQUEADO)

        class Probe(EstatisticasHibridasCompeticoes):
            def _recolher_base_tolerante(self, *_args, **_kwargs):
                raise AssertionError("Nao repetir 31 blocos ESPN HTTP 400")
            def _consultar_intervalo(self, *_args, **_kwargs):
                raise AssertionError("Nao consultar ESPN neste caminho")

        for codigo, tid in (("uefa.champions", 7), ("por.taca.portugal", 336)):
            with self.subTest(codigo=codigo):
                sofa = SofaHistoricoFake()
                stats = Probe(sofa_client=sofa)
                resultados = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(resultados), 24)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore")
                self.assertIn(f"/unique-tournament/{tid}/seasons", sofa.chamadas)
                self.assertEqual(len(sofa.chamadas), 2)
                self.assertEqual(resultados[0]["golos_casa"], 2)
                self.assertEqual(resultados[0]["golos_fora"], 1)
                self.assertEqual(resultados[0]["liga_codigo"], codigo)
                self.assertTrue(all(x["timestamp"] < REF.timestamp() for x in resultados))

    def test_epoca_errada_e_recusada_sem_fabricar_dados(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                stats = EstatisticasHibridasCompeticoes(sofa_client=SofaHistoricoFake(temporada="25/26"))
                with self.assertRaises(ValueError):
                    stats._fetch_liga(codigo, REF)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore_indisponivel")

    def test_base_inferior_ao_minimo_nao_produz_previsao(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                stats = EstatisticasHibridasCompeticoes(sofa_client=SofaHistoricoFake(total=9))
                with self.assertRaises(ValueError):
                    stats._fetch_liga(codigo, REF)
                self.assertIn("base insuficiente", stats.diagnostico_base[codigo]["motivo"])

    def test_erro_parcial_nao_aceita_resultados_inventados(self):
        stats = EstatisticasHibridasCompeticoes(sofa_client=SofaHistoricoFake(erro_pagina=True))
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.champions", REF)
        self.assertEqual(stats.diagnostico_base["uefa.champions"]["jogos"], 0)

    def test_group_stage_ambiguo_nao_vira_champions(self):
        evento = {
            "id": "1234567",
            "date": "2026-10-14T19:45:00Z",
            "league": {"name": "Group Stage"},
            "season": {"name": "Group Stage"},
            "status": {"type": {"state": "pre"}},
            "competitions": [{
                "league": {"name": "Group Stage"},
                "competitors": [
                    {"homeAway": "home", "team": {"id": "1", "name": "Equipa A"}},
                    {"homeAway": "away", "team": {"id": "2", "name": "Equipa B"}},
                ],
            }],
        }
        jogo = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(jogo["liga"], "Group Stage")
        self.assertIsNone(EstatisticasESPNEnriquecidas.resolver_liga(jogo))
        evento["season"]["slug"] = "2026-27-uefa-champions-league"
        reconhecido = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(reconhecido["liga"], "UEFA Champions League")
        self.assertEqual(EstatisticasESPNEnriquecidas.resolver_liga(reconhecido), "uefa.champions")

    def test_ano_alvo_portugal_e_champions_cruzam_epoca(self):
        stats = EstatisticasHibridasCompeticoes(sofa_client=SofaHistoricoFake())
        for codigo in ("uefa.champions", "por.taca.portugal"):
            self.assertEqual(stats._ano_alvo_sofa(codigo, REF), "26/27")
            janeiro = datetime(2027, 1, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
            self.assertEqual(stats._ano_alvo_sofa(codigo, janeiro), "26/27")


if __name__ == "__main__":
    unittest.main()
