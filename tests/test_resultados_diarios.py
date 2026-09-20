import tempfile
import unittest
from pathlib import Path

from main_diario import RegistoPrevisoesDiario


class FakeResponse:
    def __init__(self, events):
        self._events = events

    def raise_for_status(self):
        return None

    def json(self):
        return {"events": self._events}


class FakeSession:
    def __init__(self):
        self.datas = []

    def get(self, *args, **kwargs):
        data = (kwargs.get("params") or {}).get("dates")
        self.datas.append(data)
        if data == "20260914":
            return FakeResponse(
                [
                    {
                        "id": "123",
                        "status": {"type": {"state": "post", "completed": True}},
                        "competitions": [
                            {
                                "competitors": [
                                    {"homeAway": "home", "score": "2"},
                                    {"homeAway": "away", "score": "1"},
                                ]
                            }
                        ],
                    }
                ]
            )
        return FakeResponse([])




class FakeSessionFallbackLiga:
    def __init__(self):
        self.chamadas = []

    def get(self, url, *args, **kwargs):
        data = (kwargs.get("params") or {}).get("dates")
        self.chamadas.append((url, data))
        if "/eng.2/scoreboard" in url and data == "20260919":
            return FakeResponse(
                [
                    {
                        "id": "456",
                        "status": {"type": {"state": "post", "completed": True}},
                        "competitions": [
                            {
                                "competitors": [
                                    {"homeAway": "home", "score": "1"},
                                    {"homeAway": "away", "score": "1"},
                                ]
                            }
                        ],
                    }
                ]
            )
        return FakeResponse([])


class ResultadosDiariosTests(unittest.TestCase):
    def test_procura_evento_em_datas_adjacentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessao = FakeSession()
            reg = RegistoPrevisoesDiario(
                Path(tmp) / "previsoes.json", session=sessao
            )
            resultados = reg._resultados_espn("2026-09-15")

        self.assertEqual(resultados[123], (2, 1))
        self.assertEqual(
            sessao.datas,
            ["20260914", "20260915", "20260916"],
        )

    def test_fallback_por_liga_quando_all_omite_evento(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessao = FakeSessionFallbackLiga()
            reg = RegistoPrevisoesDiario(
                Path(tmp) / "previsoes.json", session=sessao
            )
            reg.dados = {
                "versao": 1,
                "previsoes": [
                    {
                        "event_id": 456,
                        "data_jogo": "2026-09-19",
                        "liga": "English League Championship",
                        "mercado": "Ambas Marcam",
                        "probabilidade": 0.60,
                        "qualidade": 75,
                        "odd_justa": 1.67,
                        "odd_minima": 1.75,
                        "estado": "pendente",
                        "resultado_binario": None,
                    }
                ],
            }

            resultados = reg._resultados_espn("2026-09-19")

        self.assertEqual(resultados[456], (1, 1))
        self.assertTrue(
            any(
                "/eng.2/scoreboard" in url and data == "20260919"
                for url, data in sessao.chamadas
            )
        )


if __name__ == "__main__":
    unittest.main()
