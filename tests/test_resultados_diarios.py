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


if __name__ == "__main__":
    unittest.main()
