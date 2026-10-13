"""Painel e observatorio de CLV: somente leitura, deduplicacao e owner-only."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from clv_observatorio import ObservatorioCLV
from main_competicoes import BotPremiumDiarioCompeticoes
from previsoes_premium import RegistoPrevisoes


class ObservatorioCLVTests(unittest.TestCase):
    @staticmethod
    def _registo(tmp, start=None):
        inicio = start or datetime(2030, 1, 2, 13, 0, tzinfo=timezone.utc)
        reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
        reg.V13_COMERCIAL_START_SNAPSHOT = 1
        reg.registar([
            {
                "jogo": {
                    "id": 9990,
                    "casa": "Equipa A",
                    "fora": "Equipa B",
                    "liga": "Liga Teste",
                    "timestamp": inicio.timestamp(),
                },
                "mercado": "Under 2.5 Golos",
                "probabilidade": 0.61,
                "probabilidade_bruta": 0.63,
                "qualidade": 80,
                "odd_justa": 1.64,
                "odd_minima": 1.72,
                "odd_real": 1.80,
                "ranking_modelo": 2,
                "confianca": "MEDIA",
                "score": 0.61,
            },
        ])
        return reg, inicio

    def test_estados_clv_sao_apenas_leitura(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            obs = ObservatorioCLV(Path(tmp) / "avisos.json")
            original = copy.deepcopy(reg.dados)
            self.assertEqual(obs.dados(reg, inicio - timedelta(hours=1))["totais"]["antes_janela"], 1)
            self.assertEqual(obs.dados(reg, inicio - timedelta(minutes=15))["totais"]["em_janela"], 1)
            self.assertEqual(obs.dados(reg, inicio + timedelta(minutes=2))["totais"]["inicio_recente"], 1)
            self.assertEqual(obs.dados(reg, inicio + timedelta(minutes=6))["totais"]["sem_fecho"], 1)
            self.assertIn("Under 2.5", obs.relatorio(reg, inicio + timedelta(minutes=6)))
            self.assertEqual(reg.dados, original)
            self.assertFalse((Path(tmp) / "avisos.json").exists())

    def test_fecho_real_elimina_alerta_sem_inferir_valores(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            reg.dados["previsoes"][0]["odd_fecho"] = 1.75
            obs = ObservatorioCLV(Path(tmp) / "avisos.json")
            self.assertEqual(obs.dados(reg, inicio + timedelta(minutes=6))["totais"]["com_fecho"], 1)
            avisar = Mock()
            self.assertEqual(obs.avisar_fechos_em_falta(reg, avisar, inicio + timedelta(minutes=6)), 0)
            avisar.assert_not_called()

    def test_alerta_uma_vez_apos_cinco_minutos_mesmo_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            marker = Path(tmp) / "avisos.json"
            emitir = Mock()
            obs = ObservatorioCLV(marker)
            self.assertEqual(obs.avisar_fechos_em_falta(reg, emitir, inicio + timedelta(minutes=3)), 0)
            self.assertEqual(obs.avisar_fechos_em_falta(reg, emitir, inicio + timedelta(minutes=6)), 1)
            self.assertEqual(ObservatorioCLV(marker).avisar_fechos_em_falta(reg, emitir, inicio + timedelta(minutes=8)), 0)
            emitir.assert_called_once()
            self.assertIn("CLV EM FALTA", emitir.call_args.args[0])
            self.assertEqual(len(json.loads(marker.read_text())["avisados"]), 1)

    def test_nao_alertar_retroativamente_quando_mais_de_uma_hora(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            emitir = Mock()
            obs = ObservatorioCLV(Path(tmp) / "avisos.json")
            self.assertEqual(obs.avisar_fechos_em_falta(reg, emitir, inicio + timedelta(hours=2)), 0)
            emitir.assert_not_called()

    def test_falha_envio_permita_retry_sem_marcar_enviado(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            marker = Path(tmp) / "avisos.json"
            obs = ObservatorioCLV(marker)
            with self.assertRaises(RuntimeError):
                obs.avisar_fechos_em_falta(
                    reg, Mock(side_effect=RuntimeError("telegram offline")), inicio + timedelta(minutes=6)
                )
            self.assertFalse(marker.exists())
            self.assertEqual(obs.avisar_fechos_em_falta(reg, Mock(), inicio + timedelta(minutes=7)), 1)

    def test_marcador_corrompido_falha_fechado(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            marker = Path(tmp) / "avisos.json"
            marker.write_text("{corrompido", encoding="utf-8")
            emitir = Mock()
            with self.assertRaises(RuntimeError):
                ObservatorioCLV(marker).avisar_fechos_em_falta(
                    reg, emitir, inicio + timedelta(minutes=6)
                )
            self.assertEqual(marker.read_text(), "{corrompido")
            emitir.assert_not_called()

    def test_sem_volume_desativa_alertas(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            emitir = Mock()
            self.assertEqual(ObservatorioCLV().avisar_fechos_em_falta(
                reg, emitir, inicio + timedelta(minutes=6)
            ), 0)
            emitir.assert_not_called()

    def test_painel_admin_read_only_e_acesso_restrito(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._registo(tmp)
            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.previsoes = reg
            bot._observatorio_clv = ObservatorioCLV(Path(tmp) / "avisos.json")
            bot._agenda_analise_diaria = Mock(
                relatorio=Mock(return_value="ANALISE AUTO\nEstado: 🟢 Concluida")
            )
            bot.odds = Mock(
                status_conta=Mock(return_value={"request_count": 5, "request_limit": 5000, "remaining": 4995})
            )
            bot.username = None
            bot.owner_id = 123
            bot.chat_id = 123
            bot.enviar_mensagem = Mock()
            anterior = copy.deepcopy(reg.dados)

            bot.processar_comando(123, "/painel", user_id=999)
            bot.enviar_mensagem.assert_not_called()

            bot.processar_comando(123, "/painel", user_id=123)
            texto = bot.enviar_mensagem.call_args.args[1]
            self.assertIn("PAINEL DE CONTROLO", texto)
            self.assertIn("5/5000 usados", texto)
            self.assertIn("Entradas VALUE: 1/50", texto)

            bot.processar_comando(123, "/clv_diagnostico", user_id=123)
            self.assertIn("DIAGNOSTICO CLV", bot.enviar_mensagem.call_args.args[1])
            self.assertEqual(reg.dados, anterior)
            self.assertFalse((Path(tmp) / "avisos.json").exists())


if __name__ == "__main__":
    unittest.main()
