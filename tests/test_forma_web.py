import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from estatisticas_forma_web import EstatisticasFormaWeb


class RespostaFake:
    def __init__(self, dados=None, status=200):
        self._dados = dados or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            resposta = type("R", (), {"status_code": self.status_code})()
            raise requests.HTTPError(f"HTTP {self.status_code}", response=resposta)

    def json(self):
        return self._dados


class SessaoFake:
    def __init__(self, falhar_web=False):
        self.falhar_web = falhar_web
        self.chamadas = []

    @staticmethod
    def _evento(i, team_id=10):
        adversario = 100 + i
        casa_id, fora_id = (team_id, adversario) if i % 2 == 0 else (adversario, team_id)
        data = datetime(2026, 9, 10 - i, 18, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "id": 5000 + i,
            "date": data,
            "name": f"Jogo {i}",
            "season": {"slug": "official-league"},
            "status": {"type": {"state": "post", "completed": True, "name": "STATUS_FINAL"}},
            "competitions": [{
                "date": data,
                "competitors": [
                    {"homeAway": "home", "score": "2", "team": {"id": str(casa_id), "displayName": f"T{casa_id}"}},
                    {"homeAway": "away", "score": "1", "team": {"id": str(fora_id), "displayName": f"T{fora_id}"}},
                ],
            }],
        }

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, params))
        if "site.web.api.espn.com" in url:
            if self.falhar_web:
                return RespostaFake(status=404)
            return RespostaFake({"events": [self._evento(i) for i in range(8)]})
        if "site.api.espn.com" in url:
            return RespostaFake({"events": [self._evento(i) for i in range(8)]})
        raise AssertionError(url)


class FormaWebTests(unittest.TestCase):
    REF = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))

    def test_forma_global_usa_site_web_atual(self):
        sessao = SessaoFake()
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        self.assertEqual(len(forma), 8)
        self.assertIn("site.web.api.espn.com", sessao.chamadas[0][0])
        self.assertEqual(len(sessao.chamadas), 1)

    def test_forma_global_faz_fallback_para_host_antigo(self):
        sessao = SessaoFake(falhar_web=True)
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        self.assertEqual(len(forma), 8)
        self.assertTrue(any("site.api.espn.com" in url for url, _ in sessao.chamadas))

    def test_forma_global_mantem_ids_espn_da_equipa(self):
        sessao = SessaoFake()
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        amostra = stats._ultimos_time(forma, 10, limite=8)
        self.assertEqual(len(amostra), 8)


if __name__ == "__main__":
    unittest.main()
