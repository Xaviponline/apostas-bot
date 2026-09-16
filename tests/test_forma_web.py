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
    def __init__(self, falhar_site=False, score_objeto=False, status_na_competicao=False):
        self.falhar_site = falhar_site
        self.score_objeto = score_objeto
        self.status_na_competicao = status_na_competicao
        self.chamadas = []

    def _score(self, valor):
        if not self.score_objeto:
            return str(valor)
        return {"value": float(valor), "displayValue": str(valor)}

    def _evento(self, i, team_id=10):
        adversario = 100 + i
        casa_id, fora_id = (team_id, adversario) if i % 2 == 0 else (adversario, team_id)
        data = datetime(2026, 9, 10 - i, 18, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        status = {"type": {"state": "post", "completed": True, "name": "STATUS_FINAL"}}
        comp = {
            "date": data,
            "competitors": [
                {"homeAway": "home", "score": self._score(2), "team": {"id": str(casa_id), "displayName": f"T{casa_id}"}},
                {"homeAway": "away", "score": self._score(1), "team": {"id": str(fora_id), "displayName": f"T{fora_id}"}},
            ],
        }
        evento = {
            "id": 5000 + i,
            "date": data,
            "name": f"Jogo {i}",
            "season": {"displayName": "2026-27 Official League"},
            "league": {"name": "Official League", "slug": "official-league"},
            "competitions": [comp],
        }
        if self.status_na_competicao:
            comp["status"] = status
        else:
            evento["status"] = status
        return evento

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, params))
        if "site.api.espn.com" in url:
            if self.falhar_site:
                return RespostaFake(status=404)
            return RespostaFake({"events": [self._evento(i) for i in range(8)]})
        if "site.web.api.espn.com" in url:
            return RespostaFake({"events": [self._evento(i) for i in range(8)]})
        raise AssertionError(url)


class FormaWebTests(unittest.TestCase):
    REF = datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Lisbon"))

    def test_forma_global_usa_primeiro_rota_de_resultados_concluidos(self):
        sessao = SessaoFake()
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        self.assertEqual(len(forma), 8)
        url, params = sessao.chamadas[0]
        self.assertIn("site.api.espn.com", url)
        self.assertEqual(params, {"seasontype": 1, "type": 0, "level": 3})
        self.assertEqual(len(sessao.chamadas), 1)

    def test_forma_global_faz_fallback_para_host_web(self):
        sessao = SessaoFake(falhar_site=True)
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        self.assertEqual(len(forma), 8)
        self.assertTrue(any("site.web.api.espn.com" in url for url, _ in sessao.chamadas))

    def test_forma_global_aceita_score_como_objeto(self):
        sessao = SessaoFake(score_objeto=True)
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        self.assertEqual(len(forma), 8)
        self.assertEqual(forma[0]["golos_casa"], 2)
        self.assertEqual(forma[0]["golos_fora"], 1)

    def test_forma_global_aceita_status_na_competicao(self):
        sessao = SessaoFake(status_na_competicao=True)
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        self.assertEqual(len(forma), 8)
        diag = stats.diagnostico_forma_global[10]["tentativas"][0]
        self.assertEqual(diag["concluidos"], 8)
        self.assertEqual(diag["normalizados"], 8)

    def test_forma_global_mantem_ids_espn_da_equipa(self):
        sessao = SessaoFake()
        stats = EstatisticasFormaWeb(session=sessao)
        forma = stats._fetch_forma_global(10, self.REF)
        amostra = stats._ultimos_time(forma, 10, limite=8)
        self.assertEqual(len(amostra), 8)


if __name__ == "__main__":
    unittest.main()
