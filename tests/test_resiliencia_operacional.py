"""Testes de backups locais, rastreio passivo e vigilancia de tarefas."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from backups_locais import CopiasSeguranca
from monitor_operacional import MonitorOperacional
from odds_auditoria import AuditoriaOdds
from odds_rastreio import RastreioOdds
from main_competicoes import BotPremiumDiarioCompeticoes


TZ = ZoneInfo("Europe/Lisbon")


class BackupTests(unittest.TestCase):
    @staticmethod
    def origem(pasta):
        (pasta / "previsoes_premium.json").write_text(
            json.dumps({"versao": 1, "previsoes": [{"chave": "1|Under 2.5"}]}),
            encoding="utf-8",
        )
        (pasta / "acessos_premium.json").write_text(
            json.dumps({"clientes": {"999": {"ativo": True}}}), encoding="utf-8"
        )

    def test_backup_diario_valida_integridade_e_nao_modifica_originais(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.origem(base)
            b = CopiasSeguranca(base)
            antes = (base / "previsoes_premium.json").read_bytes()
            data = datetime(2030, 1, 10, 9, 20, tzinfo=TZ)
            self.assertTrue(b.executar_se_devido(data))
            destino = base / "backups_locais" / "2030-01-10"
            self.assertTrue(b.validar(destino))
            self.assertEqual((destino / "previsoes_premium.json").read_bytes(), antes)
            self.assertEqual((base / "previsoes_premium.json").read_bytes(), antes)
            self.assertTrue((destino / "acessos_premium.json").exists())
            self.assertFalse(b.executar_se_devido(data + timedelta(minutes=5)))
            self.assertIn("VALIDA", b.relatorio(agora=data))

    def test_backup_falha_fechado_se_ja_existe_copia_corrompida(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.origem(base)
            b = CopiasSeguranca(base)
            data = datetime(2030, 1, 10, 11, 0, tzinfo=TZ)
            self.assertTrue(b.executar_se_devido(data))
            destino = base / "backups_locais" / "2030-01-10"
            (destino / "previsoes_premium.json").write_text("corrupcao", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                b.executar_se_devido(data + timedelta(hours=1))
            self.assertEqual((destino / "previsoes_premium.json").read_text(), "corrupcao")
            self.assertIn("FALHA", b.relatorio(agora=data))

    def test_backup_antes_de_hora_nao_executa_e_falta_essencial_falha(self):
        with tempfile.TemporaryDirectory() as td:
            b = CopiasSeguranca(Path(td))
            self.assertFalse(b.executar_se_devido(datetime(2030, 1, 10, 8, 0, tzinfo=TZ)))
            with self.assertRaises(RuntimeError):
                b.executar_se_devido(datetime(2030, 1, 10, 9, 16, tzinfo=TZ))
            self.assertFalse((Path(td) / "backups_locais" / "2030-01-10").exists())

    def test_backup_retencao_maximo_catorze_dias(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.origem(base)
            b = CopiasSeguranca(base)
            for dia in range(17):
                self.assertTrue(
                    b.executar_se_devido(
                        datetime(2030, 1, 1, 10, 0, tzinfo=TZ) + timedelta(days=dia)
                    )
                )
            self.assertEqual(len(b._nomes()), 14)
            self.assertEqual(b._nomes()[0].name, "2030-01-17")
            self.assertFalse((base / "backups_locais" / "2030-01-01").exists())
            self.assertTrue((base / "previsoes_premium.json").exists())


class RastreioTests(unittest.TestCase):
    def test_referencias_unicas_sem_mudar_valor_ou_resultado(self):
        dados = {
            "casa": "Cardiff City", "fora": "Watford",
            "mercados": [{
                "id": "mercado-77", "name": "Total Goals",
                "handicap": 2.5, "period": "fulltime", "updatedAt": "2030-01-01T12:00:00Z",
                "odds": [{"odd": 2.25, "seleção": "Under", "ref": "u_25",
                          "bookmakerChangedAt": "2030-01-01T12:00:00Z"}],
            }],
        }
        antes = copy.deepcopy(dados)
        auditoria = AuditoriaOdds(None)
        extraida, motivo = auditoria._extrair_odd_diagnostico(dados, "Under 2.5 Golos")
        self.assertIsNone(motivo)
        self.assertEqual(extraida[0], 2.25)
        meta = auditoria._referencias_cotacao(dados, "Under 2.5 Golos", *extraida)
        self.assertEqual(meta["market_id"], "mercado-77")
        self.assertEqual(meta["outcome_ref"], "u_25")
        self.assertEqual(meta["association"], "unica")
        self.assertEqual(dados, antes)

    def test_rastreio_local_sem_segredos_e_sem_mutar_selecoes(self):
        with tempfile.TemporaryDirectory() as td:
            r = RastreioOdds(Path(td) / "odds_rastreio.jsonl")
            s = [{
                "jogo": {"id": 50, "casa": "Cardiff", "fora": "Watford", "timestamp": 1000},
                "mercado": "Under 2.5 Golos",
                "odd_real": 2.25,
                "odds_event_id": "fixture-22",
                "_rastreio_odds": {"market_id": "m1", "outcome_ref": "u25",
                                  "association": "unica", "selection_name": "Under"},
            }]
            antes = copy.deepcopy(s)
            self.assertEqual(r.registar(s, "CLV_AUTO"), 1)
            self.assertEqual(s, antes)
            reg = json.loads(r.path.read_text(encoding="utf-8").strip())
            self.assertEqual(reg["mercado_id_fonte"], "m1")
            self.assertEqual(reg["operacao"], "CLV_AUTO")
            self.assertNotIn("apiKey", reg)
            self.assertIn("RASTREIO ODDS", r.relatorio())
            self.assertEqual(r.registar([{"jogo": {}, "mercado": "x"}]), 0)


class MonitorTests(unittest.TestCase):
    @staticmethod
    def agenda(data=None):
        class FakeAgenda:
            def __init__(self, data):
                self.data = data

            def relatorio(self, agora=None):
                if self.data:
                    return "Ultima execucao automatica: " + self.data + "T09:00:00+01:00"
                return "Ultima execucao automatica: ainda sem execucoes"
        return FakeAgenda(data)

    def test_alerta_tarefas_atrasadas_uma_vez_por_dia_e_heartbeat(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            b = CopiasSeguranca(base)
            m = MonitorOperacional(base / "monitor_estado.json")
            dt = datetime(2030, 1, 10, 10, 20, tzinfo=TZ)
            enviar = Mock()
            self.assertEqual(m.verificar(self.agenda(), b, enviar, dt), 2)
            self.assertEqual(m.verificar(self.agenda(), b, enviar, dt+timedelta(minutes=5)), 0)
            enviar.assert_called_once()
            self.assertIn("backup", enviar.call_args.args[0].lower())
            self.assertIn("Heartbeat recente", m.relatorio(self.agenda(), b, dt))
            self.assertEqual(
                m.verificar(self.agenda(), b, enviar, dt + timedelta(days=1)), 2
            )

    def test_monitor_nao_emite_alarme_antes_de_1015(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            m = MonitorOperacional(base / "monitor_estado.json")
            enviar = Mock()
            dt = datetime(2030, 1, 10, 9, 10, tzinfo=TZ)
            self.assertEqual(m.verificar(self.agenda(), CopiasSeguranca(base), enviar, dt), 0)
            enviar.assert_not_called()

    def test_falha_envio_nao_queima_avisos_e_corrompido_nao_reescreve(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            estado = base / "monitor_estado.json"
            m = MonitorOperacional(estado)
            dt = datetime(2030, 1, 10, 10, 20, tzinfo=TZ)
            with self.assertRaises(RuntimeError):
                m.verificar(self.agenda(), CopiasSeguranca(base), Mock(side_effect=RuntimeError("offline")), dt)
            self.assertFalse(estado.exists())
            estado.write_text("{bad", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                m.verificar(self.agenda(), CopiasSeguranca(base), Mock(), dt)
            self.assertEqual(estado.read_text(), "{bad")

    def test_acesso_admin_restrito_nos_tres_comandos(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            BackupTests.origem(base)
            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.username = None
            bot.owner_id = bot.chat_id = 123
            bot.enviar_mensagem = Mock()
            bot._backups = CopiasSeguranca(base)
            bot._monitor = MonitorOperacional(base / "monitor_estado.json")
            bot._rastreio_odds = RastreioOdds(base / "odds_rastreio.jsonl")
            bot._agenda_analise_diaria = self.agenda()
            for comando in ("/backup_status", "/monitor_status", "/odds_rastreio"):
                bot.processar_comando(123, comando, user_id=999)
            bot.enviar_mensagem.assert_not_called()
            for comando in ("/backup_status", "/monitor_status", "/odds_rastreio"):
                bot.processar_comando(123, comando, user_id=123)
            self.assertEqual(bot.enviar_mensagem.call_count, 3)


if __name__ == "__main__":
    unittest.main()
