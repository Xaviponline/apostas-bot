"""Regressões isoladas da recuperação Europa/Conferência (15/10/2026).

Fixtures sintéticas, sem rede, sem snapshots, odds nem alterar o modelo V1.
"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


REF = datetime(2026, 10, 15, 10, tzinfo=ZoneInfo("Europe/Lisbon"))
CODIGOS = ("uefa.europa", "uefa.europa.conf")


def evento(i, data, terminou=True):
    return {
        "id": str(i), "date": data + "T19:00:00Z",
        "status": {"type": {"state": "post" if terminou else "pre", "completed": terminou}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"id": "100", "displayName": "Casa"}, "score": "2"},
            {"homeAway": "away", "team": {"id": "200", "displayName": "Fora"}, "score": "1"},
        ]}],
    }


class Resposta:
    def __init__(self, eventos): self.eventos = eventos
    def raise_for_status(self): pass
    def json(self): return {"events": list(self.eventos)}


class Sessao:
    def __init__(self, por_ano):
        self.por_ano, self.chamadas = por_ano, []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, dict(params or {})))
        return Resposta(self.por_ano[params["dates"]])


class HistoricoEuropaConferenciaTests(unittest.TestCase):
    def test_ambas_rotas_anuais_preservam_fonte_e_corte(self):
        class Probe(EstatisticasHibridasCompeticoes):
            def _fetch_base_sofa(self, *args):
                raise AssertionError("SofaScore nao deve ser preciso se ESPN respondeu")
            def _consultar_intervalo(self, *args):
                raise AssertionError("ESPN dates por intervalo nao devem ser usados")

        jogos = ([evento(i, "2026-10-08") for i in range(24)]
                 + [evento(900, "2026-10-15")]
                 + [evento(901, "2026-10-16", terminou=False)])
        for codigo in CODIGOS:
            with self.subTest(codigo=codigo):
                sessao = Sessao({"2026": jogos})
                stats = Probe(session=sessao)
                base = stats._fetch_liga(codigo, REF)
                self.assertEqual(len(base), 24)
                self.assertEqual(stats.diagnostico_base[codigo]["fonte"], "espn_anual")
                self.assertTrue(all(j["liga_codigo"] == codigo for j in base))
                self.assertTrue(all(j["timestamp"] < REF.timestamp() for j in base))
                self.assertEqual(len(sessao.chamadas), 1)
                url, params = sessao.chamadas[0]
                self.assertIn("/" + codigo + "/scoreboard", url)
                self.assertEqual(params, {"dates": "2026", "limit": 500})

    def test_historico_curto_nao_gera_base_falsa(self):
        class Probe(EstatisticasHibridasCompeticoes):
            def _fetch_base_sofa(self, *args):
                raise ValueError("Sofa indisponivel no teste")

        for codigo in CODIGOS:
            with self.subTest(codigo=codigo):
                sessao = Sessao({
                    "2026": [evento(i, "2026-10-08") for i in range(3)],
                    "2025": [evento(i + 100, "2025-11-09") for i in range(2)],
                })
                stats = Probe(session=sessao)
                with self.assertRaisesRegex(ValueError, "Sofa indisponivel"):
                    stats._fetch_liga(codigo, REF)
                self.assertEqual(
                    stats.diagnostico_base[codigo]["fonte"],
                    "ambas_fontes_indisponiveis",
                )
                self.assertEqual(
                    [x[1]["dates"] for x in sessao.chamadas], ["2026", "2025"]
                )

    def test_sem_mudar_rotas_de_competicoes_ja_validadas(self):
        stats = EstatisticasHibridasCompeticoes()
        self.assertIn("uefa.champions", stats.ESPN_HISTORICO_ANUAL)
        self.assertIn("por.taca.portugal", stats.ESPN_HISTORICO_ANUAL)
        for codigo in CODIGOS:
            self.assertIn(codigo, stats.ESPN_HISTORICO_ANUAL)
        self.assertNotIn("eng.3", stats.ESPN_HISTORICO_ANUAL)


if __name__ == "__main__":
    unittest.main()
