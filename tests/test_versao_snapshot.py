import tempfile
import time
import unittest
from pathlib import Path

from previsoes_premium import RegistoPrevisoes


class VersaoSnapshotTests(unittest.TestCase):
    def _selecao(self, event_id=12345):
        return {
            "jogo": {
                "id": event_id,
                "casa": "Casa",
                "fora": "Fora",
                "liga": "English Premier League",
                "timestamp": time.time() + 3600,
            },
            "mercado": "Vitória Casa",
            "probabilidade": 0.61,
            "probabilidade_bruta": 0.63,
            "qualidade": 75,
            "odd_justa": 1.64,
            "odd_minima": 1.72,
        }

    def test_nova_previsao_recebe_versao_v11(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            adicionadas = reg.registar([self._selecao()])

            self.assertEqual(adicionadas, 1)
            self.assertEqual(reg.dados["previsoes"][0]["modelo_versao"], "V1.1")

    def test_registo_legacy_nao_e_reescrito_com_versao(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            legado = {
                "chave": "12345|Vitória Casa",
                "event_id": 12345,
                "mercado": "Vitória Casa",
                "estado": "pendente",
                "timestamp_jogo": time.time() + 3600,
                "probabilidade": 0.61,
            }
            reg.dados = {"versao": 1, "previsoes": [legado]}
            reg.registar([self._selecao()])

            self.assertNotIn("modelo_versao", legado)
            self.assertEqual(len(reg.dados["previsoes"]), 1)


if __name__ == "__main__":
    unittest.main()
