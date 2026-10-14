"""Regressões da rota ESPN anual, com dados totalmente sintéticos.

Não calcular seleções, alterar parâmetros, escrever snapshots nem ligar à rede.
"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes


REF = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))


def evento_espn(identificador, data_iso, terminado=True):
    return {
        "id": str(identificador),
        "date": data_iso + "T19:00:00Z",
        "status": {"type": {
            "state": "post" if terminado else "pre",
            "completed": terminado,
        }},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {
                "id": "100", "displayName": "Equipa da Casa",
            }, "score": "2"},
            {"homeAway": "away", "team": {
                "id": "200", "displayName": "Equipa de Fora",
            }, "score": "1"},
        ]}],
    }


class RespostaAnualFake:
    def __init__(self, eventos):
        self.eventos = eventos

    def raise_for_status(self):
        pass

    def json(self):
        return {"events": list(self.eventos)}


class SessaoESPNAnualFake:
    def __init__(self, por_ano):
        self.por_ano = por_ano
        self.chamadas = []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, dict(params or {})))
        ano = (params or {}).get("dates")
        if ano not in self.por_ano:
            raise AssertionError(f"Ano inesperado: {ano}")
        return RespostaAnualFake(self.por_ano[ano])


class ESPNAnualShadowTests(unittest.TestCase):
    def test_ano_unico_preserva_corte_de_ontem_sem_sofascore(self):
        class Probe(EstatisticasHibridasCompeticoes):
            def _sofa_get(self, caminho):
                raise AssertionError("SofaScore não deve ser contactado")

            def _consultar_intervalo(self, *args):
                raise AssertionError("ESPN por intervalos não deve ser usada")

        eventos = (
            [evento_espn(i, "2026-10-13") for i in range(24)]
            + [evento_espn(90, "2026-10-14")]
            + [evento_espn(91, "2026-10-18", terminado=False)]
            + [evento_espn(92, "2026-10-12", terminado=False)]
        )
        for liga in ("uefa.champions", "por.taca.portugal"):
            with self.subTest(liga=liga):
                sessao = SessaoESPNAnualFake({"2026": eventos})
                stats = Probe(session=sessao)
                historico = stats._fetch_liga(liga, REF)
                self.assertEqual(len(historico), 24)
                self.assertTrue(all(x["timestamp"] < REF.timestamp() for x in historico))
                self.assertTrue(all(x["id"] < 24 for x in historico))
                self.assertEqual(stats.diagnostico_base[liga]["fonte"], "espn_anual")
                self.assertEqual(stats.diagnostico_base[liga]["anos_consultados"], [2026])
                self.assertEqual(len(sessao.chamadas), 1)
                self.assertEqual(sessao.chamadas[0][1]["dates"], "2026")
                self.assertEqual(len(stats._fetch_liga(liga, REF)), 24)
                self.assertEqual(len(sessao.chamadas), 1)  # cache local

    def test_consulta_ano_anterior_se_2026_nao_chega_ao_minimo(self):
        eventos_2026 = [evento_espn(i, "2026-10-10") for i in range(4)]
        eventos_2025 = [evento_espn(i + 100, "2025-11-15") for i in range(24)]
        sessao = SessaoESPNAnualFake({
            "2026": eventos_2026, "2025": eventos_2025
        })
        stats = EstatisticasHibridasCompeticoes(session=sessao)
        historico = stats._fetch_base_espn_anual("uefa.champions", REF)
        self.assertGreaterEqual(len(historico), 24)
        self.assertEqual([p[1]["dates"] for p in sessao.chamadas], ["2026", "2025"])
        self.assertTrue(all(x["timestamp"] < REF.timestamp() for x in historico))

    def test_amostra_sem_dez_resultados_e_recusada(self):
        sessao = SessaoESPNAnualFake({
            "2026": [evento_espn(i, "2026-10-13") for i in range(5)],
            "2025": [],
        })
        stats = EstatisticasHibridasCompeticoes(session=sessao)
        with self.assertRaisesRegex(ValueError, "base ESPN anual insuficiente"):
            stats._fetch_base_espn_anual("por.taca.portugal", REF)
        self.assertEqual(stats.diagnostico_base["por.taca.portugal"]["jogos"], 5)

    def test_resposta_possivelmente_truncada_falha_fechado(self):
        sessao = SessaoESPNAnualFake({
            "2026": [evento_espn(i, "2026-10-13") for i in range(500)],
        })
        stats = EstatisticasHibridasCompeticoes(session=sessao)
        with self.assertRaisesRegex(ValueError, "paginação"):
            stats._fetch_base_espn_anual("uefa.champions", REF)


if __name__ == "__main__":
    unittest.main()
