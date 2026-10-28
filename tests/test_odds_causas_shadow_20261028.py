"""Testes sem rede: contagens de cobertura são apenas diagnóstico SHADOW."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from odds_auditoria import AuditoriaOdds
from odds_rastreio import RastreioOdds


class FonteFalsa:
    configurada = True
    nome_fonte = "Fonte falsa"

    def __init__(self, mercados):
        self.mercados = mercados
        self.consultas = 0

    def eventos_hoje(self):
        return [{
            "id": "fixture-10", "casa": "Casa", "fora": "Fora",
            "liga": "Liga Teste", "data": "2026-10-28T19:00:00Z",
        }]

    def odds_evento(self, event_id):
        self.consultas += 1
        return {
            "id": event_id, "casa": "Casa", "fora": "Fora",
            "liga": "Liga Teste", "bookmaker_disponivel": True,
            "mercados": self.mercados,
        }


def selecao(mercado="Under 2.5 Golos"):
    return {
        "jogo": {
            "id": "interno-10", "casa": "Casa", "fora": "Fora",
            "liga": "Liga Teste",
            "timestamp": datetime(2026, 10, 28, 19, tzinfo=timezone.utc).timestamp(),
        },
        "mercado": mercado, "probabilidade": 0.60,
    }


class DiagnosticoShadowTests(unittest.TestCase):
    def test_catalogo_ausente_fica_contado_sem_odd_inventada(self):
        fonte = FonteFalsa([{
            "name": "Market 999", "period": "fulltime",
            "odds": [{"seleção": "Under", "odd": 1.85}],
        }])
        res = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        self.assertEqual(res["_odds_diag"], "mercado_nao_disponivel")
        self.assertEqual(res["_odds_contexto_mercados"],
                         {"total": 1, "compativeis": 0, "sem_catalogo": 1})
        self.assertNotIn("odd_real", res)
        with tempfile.TemporaryDirectory() as tmp:
            trac = RastreioOdds(Path(tmp) / "trace.jsonl")
            self.assertEqual(trac.registar([res]), 1)
            stored = json.loads(trac.path.read_text().strip())
            self.assertEqual(stored["contexto_mercados"]["sem_catalogo"], 1)
            self.assertIn("Sem catálogo: 1", trac.detalhe("Casa"))
        self.assertEqual(fonte.consultas, 1)

    def test_mercado_presente_linha_errada_nao_gera_odd(self):
        fonte = FonteFalsa([{
            "name": "Over Under Full Time", "handicap": 3.5,
            "period": "fulltime", "odds": [
                {"seleção": "Under", "ref": "3.5/under", "odd": 1.85}
            ],
        }])
        res = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        self.assertEqual(res["_odds_diag"], "linha_ou_selecao_nao_disponivel")
        self.assertEqual(res["_odds_contexto_mercados"],
                         {"total": 1, "compativeis": 1, "sem_catalogo": 0})
        self.assertNotIn("odd_real", res)
        self.assertEqual(fonte.consultas, 1)

    def test_contagens_inseguras_nao_sao_armazenadas(self):
        s = selecao()
        s["_odds_diag"] = "mercado_nao_disponivel"
        s["_odds_contexto_mercados"] = {
            "total": True, "compativeis": -2, "sem_catalogo": 100000,
        }
        with tempfile.TemporaryDirectory() as tmp:
            rastreio = RastreioOdds(Path(tmp) / "trace.jsonl")
            rastreio.registar([s])
            gravado = json.loads(rastreio.path.read_text().strip())
            self.assertEqual(gravado["contexto_mercados"], {})


if __name__ == "__main__":
    unittest.main()
