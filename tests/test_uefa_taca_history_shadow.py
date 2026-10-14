"""Ensaios offline da recuperacao UCL/Taca: sem mexer em snapshots V1.3."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from main_enriquecido import EstatisticasESPNEnriquecidas


REFERENCIA = datetime(2026, 10, 14, 17, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


class FonteSoFaFalsa:
    def __init__(self, qtd=24, epoca="26/27"):
        self.qtd = qtd
        self.epoca = epoca
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        for codigo, nome in ((7, "UEFA Champions League"), (336, "Taça de Portugal")):
            if caminho == f"/unique-tournament/{codigo}/seasons":
                return {
                    "seasons": [
                        {"id": codigo + 96000, "name": f"{nome} {self.epoca}", "year": self.epoca}
                    ]
                }
            if caminho == f"/unique-tournament/{codigo}/season/{codigo+96000}/events/last/0":
                momento = datetime(2026, 10, 1, 21, tzinfo=timezone.utc).timestamp()
                return {
                    "events": [
                        {
                            "id": codigo * 100000 + n,
                            "startTimestamp": momento - n * 21600,
                            "status": {"type": "finished", "code": 100},
                            "homeTeam": {"id": 1000 + n, "name": f"Home {n}"},
                            "awayTeam": {"id": 2000 + n, "name": f"Away {n}"},
                            "homeScore": {"normaltime": 2},
                            "awayScore": {"normaltime": 1},
                        }
                        for n in range(self.qtd)
                    ],
                    "hasNextPage": False,
                }
        raise RuntimeError("Rota mock desconhecida")


class BloqueioESPN(EstatisticasHibridasCompeticoes):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.consultas_espn = []

    def _consultar_intervalo(self, codigo, inicio, fim):
        self.consultas_espn.append((codigo, inicio, fim))
        resposta = requests.Response()
        resposta.status_code = 400
        raise requests.HTTPError("HTTP 400", response=resposta)


class CoberturaUEFATacaShadowTests(unittest.TestCase):
    def test_id_publico_das_duas_competicoes(self):
        stats = BloqueioESPN(sofa_client=FonteSoFaFalsa())
        self.assertEqual(stats.SOFA_TOURNAMENT_IDS["uefa.champions"], 7)
        self.assertEqual(stats.SOFA_TOURNAMENT_IDS["por.taca.portugal"], 336)
        self.assertNotIn("uefa.champions", stats.ESPN_HISTORICO_BLOQUEADO)
        self.assertNotIn("por.taca.portugal", stats.ESPN_HISTORICO_BLOQUEADO)

    def test_http400_uma_sondagem_por_prova_e_sofa_aceita_base_suficiente(self):
        for codigo, ident in (("uefa.champions", 7), ("por.taca.portugal", 336)):
            with self.subTest(codigo=codigo):
                sofa = FonteSoFaFalsa()
                stats = BloqueioESPN(sofa_client=sofa)
                historico = stats._fetch_liga(codigo, REFERENCIA)
                self.assertEqual(len(stats.consultas_espn), 1)
                self.assertEqual(len(historico), 24)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore")
                self.assertTrue(all(j["liga_codigo"] == codigo for j in historico))
                self.assertIn(f"/unique-tournament/{ident}/seasons", sofa.chamadas)
                self.assertTrue(any(f"/unique-tournament/{ident}/season/" in p for p in sofa.chamadas))
                self.assertEqual(len({j["id"] for j in historico}), 24)

    def test_base_insuficiente_falha_fechado_e_nao_cria_probabilidades(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                stats = BloqueioESPN(sofa_client=FonteSoFaFalsa(qtd=9))
                with self.assertRaises(ValueError):
                    stats._fetch_liga(codigo, REFERENCIA)
                self.assertEqual(len(stats.consultas_espn), 1)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore_indisponivel")
                self.assertEqual(stats.diagnostico_base[codigo]["jogos"], 0)

    def test_epoca_diferente_nao_e_aceite(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                stats = BloqueioESPN(sofa_client=FonteSoFaFalsa(epoca="25/26"))
                with self.assertRaises(ValueError):
                    stats._fetch_liga(codigo, REFERENCIA)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore_indisponivel")

    def test_400_isolado_de_outras_competicoes_sem_atalho_novo(self):
        stats = BloqueioESPN(sofa_client=FonteSoFaFalsa())
        por_id, diag, erro = stats._recolher_base_tolerante(
            "eng.fa", REFERENCIA.date().replace(day=1), REFERENCIA.date().replace(day=14)
        )
        self.assertEqual(diag["blocos_falha"], 1)
        # eng.fa fora da lista especial: fez duas tentativas do mesmo bloco.
        self.assertEqual(len(stats.consultas_espn), 2)
        self.assertIsNotNone(erro)
        self.assertEqual(por_id, {})

    def test_group_stage_sem_slug_comprovado_continua_fora_de_cobertura(self):
        evento = {
            "id": "222",
            "date": "2026-10-14T19:45:00Z",
            "league": {"name": "Group Stage"},
            "season": {"name": "Group Stage", "slug": ""},
            "status": {"type": {"state": "pre"}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"id": "10", "displayName": "Casa"}},
                {"homeAway": "away", "team": {"id": "11", "displayName": "Fora"}},
            ]}],
        }
        jogo = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(jogo["liga"], "Group Stage")
        self.assertIsNone(EstatisticasESPNEnriquecidas.resolver_liga(jogo))
        evento["season"]["slug"] = "2026-27-uefa-champions-league"
        confirmado = BuscadorJogosReais._normalizar_evento_espn(evento)
        self.assertEqual(confirmado["liga"], "UEFA Champions League")
        self.assertEqual(EstatisticasESPNEnriquecidas.resolver_liga(confirmado), "uefa.champions")


if __name__ == "__main__":
    unittest.main()
