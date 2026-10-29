"""Testes offline das ligas e linhas 3.5 do Scout SHADOW (sem HTTP real)."""
import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from odds_referencia_shadow import _mercado_modelo, _recolher, _selecao
from scout_shadow import (
    LIMITE_LOCAL_MES, MAX_LIGAS_DIA, ScoutShadow,
    _liga, _possiveis, _registo,
)

AGORA = datetime(2026, 10, 29, 9, 5, tzinfo=timezone.utc)
INICIO = datetime(2026, 10, 29, 19, 45, tzinfo=timezone.utc)


def snap(**updates):
    item = {
        "chave": "jogo|Under 3.5 Golos",
        "event_id": 909, "timestamp_jogo": INICIO.timestamp(),
        "data_jogo": "2026-10-29", "casa": "Frosinone",
        "fora": "Lecce", "liga": "Italian Serie B",
        "mercado": "Under 3.5 Golos",
        "ranking_modelo": 2, "estado": "pendente",
        "probabilidade": .69, "qualidade": 85,
        "odd_minima": 1.5,
        "snapshot_hash": "SEL_TEST_20261029",
    }
    item.update(updates)
    return item


def evento():
    return {
        "id": "teste-evento-20261029",
        "home_team": "Frosinone", "away_team": "Lecce",
        "commence_time": INICIO.isoformat(),
        "bookmakers": [
            {
                "key": key,
                "markets": [{
                    "key": "totals", "last_update": "2026-10-29T09:01:00Z",
                    "outcomes": [
                        {"name": "Under", "point": 3.5, "price": price},
                        {"name": "Over", "point": 3.5, "price": 2.45},
                        {"name": "Under", "point": 2.5, "price": 3.10},
                        {"name": "Over", "point": 8.5, "price": 9.99},
                    ],
                }],
            }
            for key, price in (("casa_a", 1.82), ("casa_b", 1.86), ("casa_c", 1.90))
        ],
    }


class ScoutCoberturaExpandidaTests(unittest.TestCase):
    def test_chaves_sport_reais_sem_associar_tacas(self):
        casos = {
            "Swedish Allsvenskan": "soccer_sweden_allsvenskan",
            "Sweden Allsvenskan": "soccer_sweden_allsvenskan",
            "Swedish Superettan": "soccer_sweden_superettan",
            "Italian Serie B": "soccer_italy_serie_b",
            "Serie B - Italy": "soccer_italy_serie_b",
            "Brazilian Serie A": "soccer_brazil_campeonato",
            "Campeonato Brasileiro Serie A": "soccer_brazil_campeonato",
            "Brazilian Serie B": "soccer_brazil_serie_b",
            "Scottish Premiership": "soccer_spl",
        }
        for nome, chave in casos.items():
            with self.subTest(nome=nome):
                self.assertEqual(_liga(snap(liga=nome)), chave)
        for ambiguo in (
            "Serie B", "Swedish Cup", "Scottish Cup",
            "Brazilian Cup", "Swedish League One", "Allsvenskan Hockey",
        ):
            with self.subTest(ambigua=ambiguo):
                self.assertIsNone(_liga(snap(liga=ambiguo)))

    def test_under_3_5_elegivel_com_snapshot_inalterado(self):
        original = snap()
        anterior = copy.deepcopy(original)
        candidatos, motivos = _possiveis([original], AGORA)
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0][0], "soccer_italy_serie_b")
        self.assertEqual(motivos["mercado_nao_coberto"], 0)
        self.assertEqual(original, anterior)

    def test_mercados_golos_exatos_e_rejeitar_linhas_nao_suportadas(self):
        for linha in ("Over 2.5 Golos", "Under 2.5 Golos",
                      "Over 3.5 Golos", "Under 3.5 Golos"):
            with self.subTest(linha=linha):
                self.assertEqual(_mercado_modelo({"mercado": linha}), linha)
        for linha in ("Over 8.5 Golos", "Over 3.0 Golos",
                      "Over 4.5 Golos", "Under 3.55 Golos",
                      "Under Golos", "Over 2.5 Cantos"):
            with self.subTest(linha_invalida=linha):
                self.assertIsNone(_mercado_modelo({"mercado": linha}))

    def test_outcomes_3_5_nao_misturam_preco_2_5_ou_8_5(self):
        e = evento()
        cotacoes, *_ = _recolher(e, AGORA)
        self.assertEqual(cotacoes["Under 3.5 Golos"], {
            "casa_a": 1.82, "casa_b": 1.86, "casa_c": 1.90,
        })
        self.assertEqual(cotacoes["Under 2.5 Golos"], {
            "casa_a": 3.10, "casa_b": 3.10, "casa_c": 3.10,
        })
        self.assertNotIn("Over 8.5 Golos", cotacoes)
        self.assertEqual(_selecao({"key": "totals"},
                                  {"name": "Over", "point": 3.5},
                                  "Frosinone", "Lecce"), "Over 3.5 Golos")

    def test_scout_guarda_apenas_referencia_multi_casa(self):
        p = snap()
        before = copy.deepcopy(p)
        row, erro = _registo(p, evento(), "soccer_italy_serie_b", AGORA)
        self.assertIsNone(erro)
        self.assertEqual(row["mercado"], "Under 3.5 Golos")
        self.assertEqual(row["bookmakers"], 3)
        self.assertAlmostEqual(row["odd_mediana"], 1.86)
        self.assertNotIn("odd_real", row)
        self.assertEqual(p, before)

    def test_poucas_casas_ou_linha_3_5_ausente_falham_fechado(self):
        e = evento()
        e["bookmakers"] = e["bookmakers"][:2]
        row, motivo = _registo(snap(), e, "soccer_italy_serie_b", AGORA)
        self.assertIsNone(row)
        self.assertEqual(motivo, "casas_insuficientes")
        e2 = evento()
        for b in e2["bookmakers"]:
            b["markets"][0]["outcomes"] = [{
                "name": "Under", "point": 2.5, "price": 1.80,
            }]
        row, motivo = _registo(snap(), e2, "soccer_italy_serie_b", AGORA)
        self.assertIsNone(row)
        self.assertEqual(motivo, "casas_insuficientes")

    def test_sem_liga_catalogada_zero_odds_pagas(self):
        with tempfile.TemporaryDirectory() as tmp:
            scout = ScoutShadow(Path(tmp) / "scout.json")
            calls = []
            def falsa_get(_session, path, _params):
                calls.append(path)
                if path == "/sports/":
                    return [{"key": "soccer_epl", "active": True}], None, {
                        "x-requests-remaining": "400",
                    }
                raise AssertionError("Nao pode consultar odds sem liga ativa")
            with patch("scout_shadow._get", side_effect=falsa_get):
                feito, relatorio = scout.executar([snap()], agora=AGORA, chave="TESTE")
            self.assertTrue(feito)
            self.assertEqual(calls, ["/sports/"])
            self.assertIn("liga_sem_odds_api=1", relatorio)
            self.assertEqual(MAX_LIGAS_DIA, 2)
            self.assertEqual(LIMITE_LOCAL_MES, 120)


if __name__ == "__main__":
    unittest.main()
