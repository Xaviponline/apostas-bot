"""Regressões offline: melhorar descoberta sem inventar odds ou alterar V1."""
import unittest
from unittest.mock import patch

import requests

from odds_auditoria import AuditoriaOdds
from odds_betano import OddsBetano


def selecao(casa, fora, mercado="Vitória Casa"):
    return {
        "jogo": {"id": "modelo-1", "casa": casa, "fora": fora},
        "mercado": mercado,
        "probabilidade": 0.63,
    }


class FonteComplementar:
    configurada = True
    nome_fonte = "Fonte simulada"

    def __init__(self, extras=None, base=None):
        self.extras = list(extras or [])
        self.base = list(base or [])
        self.chamadas_complementares = 0
        self.chamadas_odds = []

    def eventos_hoje(self):
        return list(self.base)

    def eventos_complementares(self):
        self.chamadas_complementares += 1
        return list(self.extras)

    def odds_evento(self, event_id):
        self.chamadas_odds.append(event_id)
        for e in self.base + self.extras:
            if e["id"] == event_id:
                return {
                    "id": event_id,
                    "casa": e["casa"],
                    "fora": e["fora"],
                    "mercados": [{
                        "name": "Full Time Result", "period": "fulltime",
                        "odds": [{"seleção": "1", "odd": 2.10}],
                    }],
                    "fonte": self.nome_fonte,
                }
        return None


class RecuperacaoOddsTests(unittest.TestCase):
    def test_aliases_especificos_nao_colidem_com_clubes_diferentes(self):
        a = AuditoriaOdds
        self.assertEqual(a._canon_equipa("Heart of Midlothian"), a._canon_equipa("Hearts FC"))
        self.assertEqual(a._canon_equipa("Union St.-Gilloise"), a._canon_equipa("Union Saint-Gilloise"))
        self.assertEqual(a._canon_equipa("CSU Craiova"), a._canon_equipa("CS Universitatea Craiova"))
        self.assertEqual(a._canon_equipa("Red Star Belgrade"), a._canon_equipa("Crvena Zvezda"))
        self.assertNotEqual(a._canon_equipa("CSU Craiova"), a._canon_equipa("FC U Craiova"))
        self.assertNotEqual(a._canon_equipa("Red Star Belgrade"), a._canon_equipa("Red Star FC"))

    def test_recupera_evento_nomes_equivalentes_so_com_fallback_explicito(self):
        fonte = FonteComplementar(extras=[{
            "id": "hearts-1", "casa": "Hearts FC", "fora": "FC Nordsjaelland",
        }])
        entrada = [selecao("Heart of Midlothian", "FC Nordsjælland")]
        normal = AuditoriaOdds(fonte).enriquecer(entrada)
        self.assertEqual(normal[0]["_odds_diag"], "evento_nao_encontrado")
        self.assertEqual(fonte.chamadas_complementares, 0)

        recuperado = AuditoriaOdds(fonte).enriquecer(
            entrada, fallback_individual_ausentes=True
        )
        self.assertEqual(recuperado[0]["odd_real"], 2.10)
        self.assertEqual(recuperado[0]["odds_event_id"], "hearts-1")
        self.assertEqual(fonte.chamadas_complementares, 1)
        self.assertNotIn("odd_real", entrada[0])

    def test_evento_de_equipa_diferente_nao_recebe_odd(self):
        fonte = FonteComplementar(extras=[{
            "id": "errado", "casa": "Hearts", "fora": "FC Porto",
        }])
        resultado = AuditoriaOdds(fonte).enriquecer(
            [selecao("Heart of Midlothian", "Nordsjaelland")],
            fallback_individual_ausentes=True,
        )
        self.assertEqual(resultado[0]["_odds_diag"], "evento_nao_encontrado")
        self.assertEqual(fonte.chamadas_odds, [])

    def test_evento_ambiguo_continua_sem_odd(self):
        extras = [
            {"id": "h1", "casa": "Hearts", "fora": "Nordsjaelland"},
            {"id": "h2", "casa": "Heart of Midlothian", "fora": "Nordsjaelland"},
        ]
        fonte = FonteComplementar(extras=extras)
        resultado = AuditoriaOdds(fonte).enriquecer(
            [selecao("Hearts", "Nordsjaelland")],
            fallback_individual_ausentes=True,
        )
        self.assertEqual(resultado[0]["_odds_diag"], "evento_ambiguo")
        self.assertEqual(fonte.chamadas_odds, [])

    def test_nao_consulta_complementar_quando_evento_ja_existe(self):
        fonte = FonteComplementar(
            base=[{"id": "b", "casa": "Portugal", "fora": "Wales"}],
            extras=[{"id": "h", "casa": "Hearts", "fora": "Nordsjaelland"}],
        )
        resultado = AuditoriaOdds(fonte).enriquecer(
            [selecao("Portugal", "Wales")],
            fallback_individual_ausentes=True,
        )
        self.assertEqual(resultado[0]["odd_real"], 2.10)
        self.assertEqual(fonte.chamadas_complementares, 0)

    def test_id_duplicado_na_descoberta_nao_substitui_evento_original(self):
        fonte = FonteComplementar(
            base=[{"id": "b", "casa": "Portugal", "fora": "Wales"}],
            extras=[{"id": "b", "casa": "Hearts", "fora": "Nordsjaelland"}],
        )
        resultado = AuditoriaOdds(fonte).enriquecer(
            [selecao("Hearts", "Nordsjaelland")],
            fallback_individual_ausentes=True,
        )
        self.assertEqual(resultado[0]["_odds_diag"], "evento_nao_encontrado")
        self.assertEqual(fonte.chamadas_odds, [])

    def test_fonte_falha_na_descoberta_complementar_sem_bloquear_analise(self):
        fonte = FonteComplementar()
        fonte.eventos_complementares = lambda: (_ for _ in ()).throw(RuntimeError("off"))
        resultado = AuditoriaOdds(fonte).enriquecer(
            [selecao("Hearts", "Nordsjaelland")],
            fallback_individual_ausentes=True,
        )
        self.assertEqual(resultado[0]["_odds_diag"], "evento_nao_encontrado")


class OddspapiComplementarTests(unittest.TestCase):
    @staticmethod
    def _fixture(event_id, start):
        return {
            "fixtureId": event_id, "participant1Name": "Hearts",
            "participant2Name": "Nordsjaelland",
            "tournamentId": 12, "startTime": start,
        }

    def test_lista_sem_status_filtra_jogos_passados_e_cacheia(self):
        fonte = OddsBetano(papi_key="teste", provider="oddspapi")
        calls = []
        def get(path, params):
            self.assertEqual(path, "/fixtures")
            calls.append(dict(params))
            if "statusId" in params:
                return [self._fixture(1, "2099-10-15T20:00:00Z")]
            return [
                self._fixture(2, "2099-10-15T20:00:00Z"),
                self._fixture(3, "2020-10-15T20:00:00Z"),
            ]
        with patch.object(fonte, "_get_papi", side_effect=get):
            base = fonte.eventos_hoje()
            recuperados = fonte.eventos_complementares()
            segunda = fonte.eventos_complementares()
        self.assertEqual([x["id"] for x in base], ["1"])
        self.assertEqual([x["id"] for x in recuperados], ["2"])
        self.assertEqual(recuperados, segunda)
        self.assertEqual(len(calls), 2)
        self.assertIn("statusId", calls[0])
        self.assertNotIn("statusId", calls[1])

    def test_erro_na_descoberta_complementar_tambem_fica_em_cooldown(self):
        fonte = OddsBetano(papi_key="teste", provider="oddspapi")
        with patch.object(fonte, "_get_papi", side_effect=requests.Timeout("offline")) as get:
            self.assertEqual(fonte.eventos_complementares(), [])
            self.assertEqual(fonte.eventos_complementares(), [])
        self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
