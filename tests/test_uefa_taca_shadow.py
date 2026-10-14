"""Ensaios isolados da correção de cobertura UEFA/Taça; sem odds ou snapshots."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from analisador_inteligente import AnalisadorInteligente
from buscador_jogos_reais import BuscadorJogosReais
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from previsoes_premium import RegistoPrevisoes


TZ = ZoneInfo("Europe/Lisbon")
REF = datetime(2026, 10, 14, 16, 0, tzinfo=TZ)


class FonteSofaIsolada:
    """Fictícia: testa protocolo e erros, NÃO simula confirmação live da API."""
    ids = {7: 91007, 336: 91336}

    def __init__(self, n=13, year="26/27"):
        self.n = n
        self.year = year
        self.chamadas = []

    def _get_sofa(self, caminho):
        self.chamadas.append(caminho)
        for tid, sid in self.ids.items():
            if caminho == f"/unique-tournament/{tid}/seasons":
                return {
                    "seasons": [
                        {"id": sid, "name": f"Teste {self.year}", "year": self.year},
                        {"id": sid - 1, "name": "Época antiga", "year": "25/26"},
                    ]
                }
            if caminho == f"/unique-tournament/{tid}/season/{sid}/events/last/0":
                eventos = []
                for i in range(self.n):
                    inicio = datetime(2026, 9, 30, 16, tzinfo=TZ) - timedelta(days=i)
                    eventos.append({
                        "id": tid * 100000 + i,
                        "startTimestamp": inicio.timestamp(),
                        "status": {"code": 100, "type": "finished"},
                        "homeTeam": {"id": 1000 + i, "name": "Equipa A"},
                        "awayTeam": {"id": 2000 + i, "name": "Equipa B"},
                        "homeScore": {"normaltime": 1, "current": 1},
                        "awayScore": {"normaltime": 2, "current": 2},
                    })
                return {"events": eventos, "hasNextPage": False}
        raise AssertionError(f"rota não esperada: {caminho}")


class ShadowCoberturaTests(unittest.TestCase):
    def test_ids_publicos_torneios_e_so_novos_codigo_bloqueados(self):
        mapping = EstatisticasHibridasCompeticoes.SOFA_TOURNAMENT_IDS
        bloqueados = EstatisticasHibridasCompeticoes.ESPN_HISTORICO_BLOQUEADO
        self.assertEqual(mapping["uefa.champions"], 7)
        self.assertEqual(mapping["por.taca.portugal"], 336)
        self.assertTrue({"uefa.champions", "por.taca.portugal"} <= bloqueados)
        self.assertNotIn("esp.1", bloqueados)
        self.assertNotIn("eng.2", bloqueados)

    def test_ambas_as_provas_usam_historico_real_ja_finalizado_e_nao_espn_bloqueada(self):
        class Sonda(EstatisticasHibridasCompeticoes):
            def _recolher_base_tolerante(self, *args, **kwargs):
                raise AssertionError("NUNCA chamar a rota histórica ESPN bloqueada")

        for codigo, unique_id in (("uefa.champions", 7), ("por.taca.portugal", 336)):
            with self.subTest(codigo=codigo):
                sofa = FonteSofaIsolada()
                stats = Sonda(sofa_client=sofa)
                historico = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(historico), 13)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore")
                self.assertEqual(stats.diagnostico_base[codigo]["torneio_id"], unique_id)
                self.assertEqual(stats.diagnostico_base[codigo]["temporada_id"], FonteSofaIsolada.ids[unique_id])
                self.assertTrue(all(x["golos_casa"] == 1 and x["golos_fora"] == 2 for x in historico))
                self.assertIn(f"/unique-tournament/{unique_id}/seasons", sofa.chamadas)

    def test_base_insuficiente_falha_fechado_sem_probabilidades_inventadas(self):
        for codigo in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(codigo=codigo):
                stats = EstatisticasHibridasCompeticoes(sofa_client=FonteSofaIsolada(n=9))
                with self.assertRaises(ValueError):
                    stats._fetch_liga(codigo, REF)
                self.assertEqual(stats.diagnostico_base[codigo]["jogos"], 0)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "sofascore_indisponivel")

    def test_epoca_25_26_nao_e_aceite_ao_pedir_26_27(self):
        stats = EstatisticasHibridasCompeticoes(sofa_client=FonteSofaIsolada(year="25/26"))
        with self.assertRaises(ValueError):
            stats._fetch_liga("uefa.champions", REF)

    def test_nao_aceita_eventos_futuros_ou_nao_terminados(self):
        stats = EstatisticasHibridasCompeticoes(sofa_client=FonteSofaIsolada())
        jogo = {
            "id": 333, "startTimestamp": REF.timestamp() + 3600,
            "status": {"type": "finished", "code": 100},
            "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 2, "name": "B"},
            "homeScore": {"normaltime": 1}, "awayScore": {"normaltime": 2},
        }
        self.assertIsNone(stats._normalizar_resultado_sofa(jogo, "uefa.champions", REF.timestamp()))
        jogo["startTimestamp"] = REF.timestamp() - 3600
        jogo["status"] = {"type": "inprogress", "code": 6}
        self.assertIsNone(stats._normalizar_resultado_sofa(jogo, "uefa.champions", REF.timestamp()))
        jogo["status"] = {"type": "finished", "code": 100}
        self.assertIsNotNone(stats._normalizar_resultado_sofa(jogo, "uefa.champions", REF.timestamp()))

    def test_group_stage_ambiguo_nunca_passa_a_champions_por_adivinhacao(self):
        e = {
            "id": "999001",
            "date": "2026-10-14T19:00:00Z",
            "season": {"name": "Group Stage"},
            "league": {"name": "Group Stage"},
            "status": {"type": {"state": "pre"}},
            "competitions": [{
                "league": {"name": "Group Stage"},
                "competitors": [
                    {"homeAway": "home", "team": {"id": "1", "displayName": "A"}},
                    {"homeAway": "away", "team": {"id": "2", "displayName": "B"}}
                ],
            }],
        }
        normalizado = BuscadorJogosReais._normalizar_evento_espn(e)
        self.assertEqual(normalizado["liga"], "Group Stage")
        self.assertIsNone(EstatisticasHibridasCompeticoes.resolver_liga(normalizado))

    def test_protocolo_comercial_e_limites_v12_nao_foram_modificados(self):
        self.assertEqual(AnalisadorInteligente.MODELO_VERSAO, "V1.2")
        self.assertEqual(AnalisadorInteligente.MAX_SELECOES, 20)
        self.assertEqual(RegistoPrevisoes.V13_COMERCIAL_START_SNAPSHOT, 207)
        self.assertEqual(RegistoPrevisoes.V13_COMERCIAL_TARGET, 50)
        self.assertEqual(RegistoPrevisoes.V13_COMERCIAL_MIN_CLV_AMOSTRAS, 40)


if __name__ == "__main__":
    unittest.main()
