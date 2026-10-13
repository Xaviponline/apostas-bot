"""Testes do agendamento diario: fuso PT, idempotencia e falhas seguras."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from analise_auto_diaria import AgendadorAnaliseDiaria
from main_sofascore import BotPremiumReal
from previsoes_premium import RegistoPrevisoes

TZ = ZoneInfo("Europe/Lisbon")


def instante(dia=14, hora=9, minuto=0):
    return datetime(2026, 10, dia, hora, minuto, tzinfo=TZ)


class AgendadorAnaliseDiariaTests(unittest.TestCase):
    def test_apenas_na_janela_portuguesa(self):
        with tempfile.TemporaryDirectory() as tmp:
            agenda = AgendadorAnaliseDiaria(Path(tmp) / "auto.json")
            acao = Mock()
            self.assertFalse(agenda.executar_se_devido(acao, instante(hora=8, minuto=59)))
            self.assertFalse(agenda.executar_se_devido(acao, instante(hora=10)))
            self.assertTrue(agenda.executar_se_devido(acao, instante()))
            acao.assert_called_once()

    def test_idempotente_mesmo_apos_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auto.json"
            acao = Mock()
            self.assertTrue(AgendadorAnaliseDiaria(path).executar_se_devido(acao, instante()))
            self.assertFalse(AgendadorAnaliseDiaria(path).executar_se_devido(acao, instante(minuto=30)))
            acao.assert_called_once()
            self.assertEqual(json.loads(path.read_text())["data"], "2026-10-14")

    def test_nova_data_pode_executar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auto.json"
            acao = Mock()
            self.assertTrue(AgendadorAnaliseDiaria(path).executar_se_devido(acao, instante(dia=14)))
            self.assertTrue(AgendadorAnaliseDiaria(path).executar_se_devido(acao, instante(dia=15)))
            self.assertEqual(acao.call_count, 2)

    def test_falha_da_analise_permite_retry_apos_10_minutos(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auto.json"
            agenda = AgendadorAnaliseDiaria(path)
            falhar = Mock(side_effect=RuntimeError("falha externa"))
            acao = Mock()
            self.assertFalse(agenda.executar_se_devido(falhar, instante()))
            self.assertFalse(agenda.executar_se_devido(acao, instante(minuto=9)))
            self.assertTrue(agenda.executar_se_devido(acao, instante(minuto=10)))
            self.assertTrue(path.exists())
            acao.assert_called_once()

    def test_marcador_corrompido_nao_se_sobrepoe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auto.json"
            path.write_text("{invalido", encoding="utf-8")
            acao = Mock()
            agenda = AgendadorAnaliseDiaria(path)
            self.assertFalse(agenda.executar_se_devido(acao, instante()))
            acao.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf-8"), "{invalido")
            self.assertIn("suspensa", agenda.relatorio(instante()))

    def test_sem_path_desativado(self):
        agenda = AgendadorAnaliseDiaria()
        acao = Mock()
        self.assertFalse(agenda.executar_se_devido(acao, instante()))
        acao.assert_not_called()

    def test_horario_de_verao_e_inverno_consistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            agenda = AgendadorAnaliseDiaria(Path(tmp) / "auto.json")
            self.assertTrue(agenda.devido(datetime(2026, 10, 14, 8, 5, tzinfo=ZoneInfo("UTC"))))
            self.assertFalse(agenda.devido(datetime(2026, 11, 14, 8, 5, tzinfo=ZoneInfo("UTC"))))

    def test_integracao_nao_reescreve_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            previsoes = RegistoPrevisoes(Path(tmp) / "previsoes.json")
            bot = BotPremiumReal(
                token="teste", gestor=object(), owner_id=1, chat_id=1,
                buscador=object(), odds=object(), analisador=object(), previsoes=previsoes,
            )
            bot._executar_analise = Mock(return_value="Analise feita")
            self.assertTrue(bot._executar_analise_auto_se_devida(instante()))
            self.assertFalse(bot._executar_analise_auto_se_devida(instante(minuto=30)))
            self.assertEqual(bot._executar_analise.call_count, 1)
            self.assertEqual(previsoes.dados.get("previsoes", []), [])
