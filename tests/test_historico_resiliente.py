import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from estatisticas_espn_resiliente import EstatisticasESPNResiliente


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else {"events": []}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class SessaoJanelaCurta:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, **kwargs):
        datas = str((params or {}).get("dates") or "")
        self.calls.append(datas)
        inicio_txt, fim_txt = datas.split("-")
        inicio = datetime.strptime(inicio_txt, "%Y%m%d").date()
        fim = datetime.strptime(fim_txt, "%Y%m%d").date()
        dias = (fim - inicio).days + 1
        if dias > 14:
            return FakeResponse(status_code=400)

        evento = {
            "id": "9001",
            "date": "2026-09-10T20:00:00Z",
            "status": {"type": {"state": "post", "completed": True}},
            "competitions": [
                {
                    "competitors": [
                        {
                            "homeAway": "home",
                            "score": "2",
                            "team": {"id": "1", "displayName": "Casa"},
                        },
                        {
                            "homeAway": "away",
                            "score": "1",
                            "team": {"id": "2", "displayName": "Fora"},
                        },
                    ]
                }
            ],
        }
        return FakeResponse({"events": [evento]})


class HistoricoResilienteTests(unittest.TestCase):
    def test_fallback_em_blocos_quando_janela_longa_falha(self):
        sessao = SessaoJanelaCurta()
        stats = EstatisticasESPNResiliente(
            session=sessao, dias_historico=30, cache_segundos=60
        )
        dados = stats._fetch_liga(
            "esp.1", datetime(2026, 9, 16, tzinfo=ZoneInfo("Europe/Lisbon"))
        )

        self.assertGreater(len(sessao.calls), 1)
        self.assertEqual(len(dados), 1)
        self.assertEqual(dados[0]["id"], 9001)
        self.assertEqual(dados[0]["liga_codigo"], "esp.1")


if __name__ == "__main__":
    unittest.main()
