"""Validação de descoberta por catálogo de participantes sem associações automáticas."""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from odds_investigacao_dirigida import investigar_fixture_por_equipa


TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 16, 22, 31, tzinfo=TZ)


def previsao():
    return {
        "data_jogo": AGORA.date().isoformat(),
        "modelo_versao": "V1.2", "ranking_modelo": 3,
        "timestamp_jogo": datetime(2030, 10, 16, 23, 30, tzinfo=TZ).timestamp(),
        "estado": "pendente", "casa": "Ponte Preta",
        "fora": "Atlético Goianiense",
        "mercado": "Under 2.5 Golos", "odd_real": None,
        "odd_minima": 1.51, "liga": "Brasileiro Serie B",
    }


def fixture(casa_id=355, fora_id=454, nome="Atlético Goianiense SAF"):
    return {
        "fixtureId": "fixture-foo", "participant1Id": casa_id,
        "participant2Id": fora_id, "participant1Name": "Ponte Preta",
        "participant2Name": nome,
        "tournamentName": "Brazil Serie B",
        "startTime": "2030-10-16T22:30:00Z",
    }


def evento(casa, casa_id, iso="2030-10-16T22:00:00Z"):
    return {"casa": casa, "fora": "Outro", "participant1_id": casa_id,
            "data": iso, "id": "abc"}


class FonteCatalogo:
    provider = "oddspapi"
    configurada = True

    def __init__(self, cache, participantes=None, resultados=None):
        self._eventos_cache = cache
        self.participantes = participantes or {}
        self.resultados = resultados or []
        self.calls = []
        self.gerais = 0

    def eventos_hoje(self):
        self.gerais += 1
        return list(self._eventos_cache or [])

    def _get_papi(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "/participants":
            return copy.deepcopy(self.participantes)
        if path == "/fixtures":
            return copy.deepcopy(self.resultados)
        raise AssertionError("Nunca consultar /odds")


class CatalogoParticipantesTests(unittest.TestCase):
    def test_ausencia_no_cache_usa_id_exato_catalogo_e_fixtures(self):
        fonte = FonteCatalogo(
            cache=[evento("Ponte Preta FC Sub-20", 99)],
            participantes={"355": "Ponte Preta", "356": "Ponte Preta Sub-20",
                           "454": "Atlético Goianiense"},
            resultados=[fixture()],
        )
        p = previsao()
        p0 = copy.deepcopy(p)
        checks = []
        def permitir(*args):
            checks.append(args)
            return True

        saida = investigar_fixture_por_equipa([p], fonte, "3", permitir, agora=AGORA)
        self.assertEqual(fonte.gerais, 0)
        self.assertEqual([x[0] for x in fonte.calls], ["/participants", "/fixtures"])
        self.assertEqual(fonte.calls[1][1]["participantId"], 355)
        self.assertIn("catálogo de participantes (nome exato)", saida)
        self.assertIn("Atlético Goianiense SAF", saida)
        self.assertIn("horário próximo", saida)
        self.assertEqual(p, p0)
        self.assertEqual(checks, [("ODDS_AUTO", 25)] * 3)

    def test_nome_parcial_na_lista_sem_id_nao_associa(self):
        fonte = FonteCatalogo(
            cache=[evento("Ponte Preta Sub-20", 9)],
            participantes={"11": "Ponte Preta Sub-20"},
            resultados=[fixture(casa_id=11)],
        )
        s = investigar_fixture_por_equipa([previsao()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("Catálogo de participantes: 0 ID(s) exato(s)", s)
        self.assertIn("nomes compatíveis 1", s)
        self.assertEqual([c[0] for c in fonte.calls], ["/participants"])

    def test_multiplos_ids_exatos_bloqueiam_fixtures(self):
        fonte = FonteCatalogo([], {"11":"Ponte Preta", "12":"Ponte Preta FC"})
        s = investigar_fixture_por_equipa([previsao()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("2 ID(s) exato(s)", s)
        self.assertEqual([c[0] for c in fonte.calls], ["/participants"])

    def test_quota_pode_bloquear_segundo_pedido(self):
        fonte = FonteCatalogo([], {"355":"Ponte Preta"}, [fixture()])
        calls = []
        def permitir(*args):
            calls.append(args)
            return len(calls) <= 2
        s = investigar_fixture_por_equipa([previsao()], fonte, "3", permitir, agora=AGORA)
        self.assertIn("suspensa após catálogo", s)
        self.assertEqual([c[0] for c in fonte.calls], ["/participants"])

    def test_id_exato_na_lista_nao_gasta_catalogo(self):
        fonte = FonteCatalogo([evento("Ponte Preta", 355)], {"355":"Ponte Preta"}, [fixture()])
        s = investigar_fixture_por_equipa([previsao()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertEqual([c[0] for c in fonte.calls], ["/fixtures"])
        self.assertIn("Origem do ID: cache da lista geral", s)

    def test_catalogo_invalido_sem_fixtures(self):
        fonte = FonteCatalogo([], {"355":"Ponte Preta"})
        fonte.participantes = ["Ponte Preta"]  # resposta inválida, não confiar
        s = investigar_fixture_por_equipa([previsao()], fonte, "3", lambda *a: True, agora=AGORA)
        self.assertIn("Catálogo de participantes inválido", s)
        self.assertEqual([c[0] for c in fonte.calls], ["/participants"])


if __name__ == "__main__":
    unittest.main()
