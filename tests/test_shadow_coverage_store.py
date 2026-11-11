"""Testes isolados da persistencia SHADOW, sem rede nem bot produtivo."""
import os
import tempfile
import unittest
from unittest.mock import patch

from shadow_coverage_store import historico_cobertura, registar_linhas


class ShadowCoverageStoreTests(unittest.TestCase):
    def test_sem_volume_nao_grava(self):
        with patch.dict(os.environ, {"DATA_DIR": ""}):
            self.assertFalse(registar_linhas("linhas soccer_epl | A | B", "🎯 LINHAS EXATAS"))
            self.assertIn("sem volume", historico_cobertura())

    def test_guarda_contagens_e_substitui_jogo(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"DATA_DIR": temp}):
                resposta = ("🎯 LINHAS EXATAS — MULTICASA SHADOW\n"
                            "• Under 2.5: 5 casas\n"
                            "• Over 2.5: 5 casas\n"
                            "• Under 3.5: 4 casas\n"
                            "• Over 3.5: 0 casas\n")
                comando = "linhas soccer_epl | A | B"
                self.assertTrue(registar_linhas(comando, resposta))
                self.assertTrue(registar_linhas(comando, resposta))
                resumo = historico_cobertura()
                self.assertIn("Jogos distintos analisados: 1", resumo)
                self.assertIn("Under 2.5: 1/1", resumo)
                self.assertIn("Over 3.5: 0/1", resumo)

    def test_nao_grava_resposta_incompleta(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"DATA_DIR": temp}):
                self.assertFalse(registar_linhas("linhas soccer_epl | A | B",
                                                "🎯 LINHAS EXATAS\n• Under 2.5: 2 casas"))
                self.assertIn("sem registos", historico_cobertura())
