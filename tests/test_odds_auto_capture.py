import tempfile
import time
import unittest
from pathlib import Path

from main_sofascore import BotPremiumReal
from previsoes_premium import RegistoPrevisoes


class GestorFake:
    dados = {"ultimo_update": 0}


class OddsFake:
    configurada = True
    nome_fonte = "Fonte Teste"

    def eventos_hoje(self):
        return [
            {
                "id": "900",
                "casa": "Casa",
                "fora": "Fora",
                "data": "2026-09-19T12:00:00Z",
            }
        ]

    def odds_evento(self, event_id):
        if str(event_id) != "900":
            return None
        return {
            "id": "900",
            "casa": "Casa",
            "fora": "Fora",
            "fonte": "Fonte Teste",
            "bookmaker_disponivel": True,
            "mercados": [
                {
                    "name": "Full Time Result",
                    "odds": [
                        {"seleção": "1", "odd": 1.80},
                        {"seleção": "X", "odd": 3.20},
                        {"seleção": "2", "odd": 4.50},
                    ],
                }
            ],
        }


class OddsAutoCaptureTests(unittest.TestCase):
    def _snapshot(self, reg, inicio_seg=3600):
        ts = time.time() + inicio_seg
        reg.registar(
            [
                {
                    "jogo": {
                        "id": 900,
                        "casa": "Casa",
                        "fora": "Fora",
                        "liga": "English Premier League",
                        "timestamp": ts,
                    },
                    "mercado": "Vitória Casa",
                    "probabilidade": 0.61,
                    "probabilidade_bruta": 0.63,
                    "qualidade": 75,
                    "odd_justa": 1.64,
                    "odd_minima": 1.72,
                }
            ]
        )
        return reg.dados["previsoes"][0]

    def _bot(self, reg):
        return BotPremiumReal(
            token="teste",
            gestor=GestorFake(),
            owner_id=1,
            chat_id=1,
            buscador=object(),
            odds=OddsFake(),
            analisador=object(),
            previsoes=reg,
        )

    def test_captura_primeira_odd_antes_do_jogo(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg)
            bot = self._bot(reg)

            capturadas = bot._capturar_odds_pendentes()

            self.assertEqual(capturadas, 1)
            self.assertEqual(snapshot["odd_real"], 1.80)
            self.assertEqual(snapshot["odds_fonte"], "Fonte Teste")
            self.assertAlmostEqual(snapshot["ev_real"], (0.61 * 1.80) - 1, places=6)

            # Uma segunda ronda não substitui nem volta a contar a odd congelada.
            self.assertEqual(bot._capturar_odds_pendentes(), 0)
            self.assertEqual(snapshot["odd_real"], 1.80)

    def test_ignora_jogo_fora_da_janela_de_seis_horas(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            snapshot = self._snapshot(reg, inicio_seg=(7 * 60 * 60))
            bot = self._bot(reg)

            self.assertEqual(bot._capturar_odds_pendentes(), 0)
            self.assertNotIn("odd_real", snapshot)

    def test_ignora_jogo_que_ja_comecou(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            # Criamos manualmente um snapshot passado para testar a seleção automática.
            snapshot = {
                "chave": "900|Vitória Casa",
                "event_id": 900,
                "data_jogo": time.strftime("%Y-%m-%d", time.localtime()),
                "timestamp_jogo": time.time() - 60,
                "casa": "Casa",
                "fora": "Fora",
                "liga": "English Premier League",
                "mercado": "Vitória Casa",
                "probabilidade": 0.61,
                "qualidade": 75,
                "odd_justa": 1.64,
                "odd_minima": 1.72,
                "estado": "pendente",
            }
            reg.dados = {"versao": 1, "previsoes": [snapshot]}
            bot = self._bot(reg)

            self.assertEqual(bot._capturar_odds_pendentes(), 0)
            self.assertNotIn("odd_real", snapshot)


if __name__ == "__main__":
    unittest.main()
