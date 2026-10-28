"""Regressões offline: diagnóstico SHADOW da linha sem aceitar odds erradas."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from odds_auditoria import AuditoriaOdds
from odds_linha_diagnostico_shadow import resumo_linha_shadow
from odds_rastreio import RastreioOdds


def mercado(handicap, lado="Over", valor=1.8):
    return {
        "name": "Over Under Full Time", "period": "fulltime",
        "handicap": handicap,
        "odds": [{"seleção": lado, "ref": lado.lower(), "odd": valor}],
    }


def resumo(mercados, mercado_modelo="Over 2.5 Golos"):
    return resumo_linha_shadow(
        mercados, mercado_modelo, AuditoriaOdds._mercado_compativel,
        AuditoriaOdds._odd_numero,
    )


class FonteFalsa:
    configurada = True
    nome_fonte = "Teste"
    consultas = 0

    def __init__(self, mercados):
        self.mercados = mercados

    def eventos_hoje(self):
        return [{"id": "id-certo", "casa": "Celtic", "fora": "Dundee United",
                 "data": "2026-10-28T18:45:00Z", "liga": "Premiership"}]

    def odds_evento(self, event_id):
        self.consultas += 1
        return {
            "id": event_id, "casa": "Celtic", "fora": "Dundee United",
            "liga": "Premiership", "bookmaker_disponivel": True,
            "mercados": self.mercados,
        }


def selecao():
    return {
        "jogo": {
            "id": "espn-id", "casa": "Celtic", "fora": "Dundee United",
            "liga": "Scottish Premiership",
            "timestamp": datetime(2026, 10, 28, 18, 45,
                                  tzinfo=timezone.utc).timestamp(),
        },
        "mercado": "Over 2.5 Golos", "probabilidade": 0.61,
    }


class DiagnosticoLinhaShadowTests(unittest.TestCase):
    def test_uma_linha_de_golos_mas_nao_a_pretendida(self):
        ms = [{"name": f"Market {i}", "odds": [{"seleção": "X", "odd": 1.5}]} for i in range(19)]
        ms.append(mercado(3.5, "Over"))
        d = resumo(ms)
        self.assertEqual(d["linhas_handicap"], [3.5])
        self.assertEqual(d["mercados_linha_alvo"], 0)
        self.assertEqual(d["mercados_outra_linha"], 1)
        self.assertEqual(d["lado_alvo_outra_linha"], 1)
        self.assertEqual(d["lado_alvo_linha_alvo"], 0)

    def test_handicap_certo_mas_lado_nao_identificado(self):
        m = mercado(2.5, "Over")
        m["odds"] = [{"seleção": "207", "ref": "codigo-sem-lado", "odd": 1.82}]
        d = resumo([m])
        self.assertEqual(d["mercados_linha_alvo"], 1)
        self.assertEqual(d["lado_desconhecido_linha_alvo"], 1)
        self.assertEqual(d["lado_alvo_linha_alvo"], 0)

    def test_handicap_ausente_nao_comprova_linha(self):
        d = resumo([mercado(None, "Over")])
        self.assertEqual(d["mercados_sem_handicap"], 1)
        self.assertEqual(d["lado_alvo_sem_handicap"], 1)
        self.assertEqual(d["mercados_linha_alvo"], 0)

    def test_nao_inventar_correspondencia_em_producao(self):
        fonte = FonteFalsa([mercado(3.5, "Over")])
        s = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        self.assertEqual(s["_odds_diag"], "linha_ou_selecao_nao_disponivel")
        self.assertNotIn("odd_real", s)
        self.assertNotIn("ev_real", s)
        self.assertEqual(fonte.consultas, 1)
        self.assertEqual(s["_odds_contexto_linha"]["linhas_handicap"], [3.5])
        with tempfile.TemporaryDirectory() as tmp:
            r = RastreioOdds(Path(tmp) / "trace.jsonl")
            r.registar([s])
            raw = json.loads(r.path.read_text().strip())
            self.assertEqual(raw["contexto_linha"]["mercados_outra_linha"], 1)
            self.assertNotIn("preco", raw["contexto_linha"])
            self.assertIn("Linhas handicap observadas: 3.5", r.detalhe("Celtic"))

    def test_mercado_realmente_valido_nao_recebe_diagnostico(self):
        fonte = FonteFalsa([mercado(2.5, "Over")])
        s = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        self.assertEqual(s["odd_real"], 1.8)
        self.assertNotIn("_odds_contexto_linha", s)
        self.assertEqual(fonte.consultas, 1)

    def test_somente_over_under_aceites(self):
        self.assertIsNone(resumo([mercado(2.5)], "Vitória Casa"))
        self.assertIsNone(resumo([mercado(2.5)], "Ambas Marcam"))


if __name__ == "__main__":
    unittest.main()
