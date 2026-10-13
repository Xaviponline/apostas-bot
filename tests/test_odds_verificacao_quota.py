"""Auditoria passiva de odds e medicao de quota sem modificar forecasts."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from odds_auditoria import AuditoriaOdds
from odds_betano import OddsBetano
from odds_quota import GestorQuotaOdds
from odds_verificacao import VerificacaoOdds
from previsoes_premium import RegistoPrevisoes
from main_competicoes import BotPremiumDiarioCompeticoes


class AuditoriaSegurancaTests(unittest.TestCase):
    @staticmethod
    def _previsoes(tmp):
        inicio = datetime(2030, 5, 10, 19, 45, tzinfo=timezone.utc)
        reg = RegistoPrevisoes(Path(tmp) / "previsoes.json")
        reg.registar([{
            "jogo": {"id": "321", "casa": "Cardiff City", "fora": "Watford",
                     "liga": "Championship", "timestamp": inicio.timestamp()},
            "mercado": "Under 2.5 Golos",
            "probabilidade": 0.608,
            "probabilidade_bruta": 0.62,
            "qualidade": 80,
            "odd_justa": 1.645,
            "odd_minima": 1.73,
            "odd_real": 2.25,
            "ranking_modelo": 4,
            "confianca": "MEDIA",
            "score": 0.608,
        }])
        return reg, inicio

    def test_cardiff_gera_alerta_sem_reescrever_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            obs = VerificacaoOdds(Path(tmp) / "odds_verificacoes.json")
            original = copy.deepcopy(reg.dados)
            aud = obs.verificacoes(reg, inicio - timedelta(hours=4))
            self.assertEqual(len(aud), 1)
            self.assertAlmostEqual(aud[0]["ev"], 0.368, places=3)
            self.assertIn("Cardiff City", obs.relatorio(reg, inicio - timedelta(hours=4)))
            self.assertEqual(reg.dados, original)

    def test_admin_alerta_uma_vez_com_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            path = Path(tmp) / "odds_verificacoes.json"
            avisos = Mock()
            agora = inicio - timedelta(minutes=90)
            self.assertEqual(VerificacaoOdds(path).avisar(reg, avisos, agora), 1)
            self.assertEqual(VerificacaoOdds(path).avisar(reg, avisos, agora), 0)
            avisos.assert_called_once()
            self.assertIn("VERIFICAR ODDS", avisos.call_args.args[0])

    def test_alerta_ausente_se_partida_comecou(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            avisar = Mock()
            self.assertEqual(VerificacaoOdds(Path(tmp)/"a.json").avisar(
                reg, avisar, inicio + timedelta(minutes=5)), 0)
            avisar.assert_not_called()

    def test_falha_de_envio_nao_marca_alerta(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            obs = VerificacaoOdds(Path(tmp)/"a.json")
            momento = inicio - timedelta(minutes=10)
            with self.assertRaises(RuntimeError):
                obs.avisar(reg, Mock(side_effect=RuntimeError("telegram offline")), momento)
            self.assertEqual(obs.avisar(reg, Mock(), momento), 1)

    def test_marcador_corrompido_nao_e_sobrescrito(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            path = Path(tmp)/"a.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                VerificacaoOdds(path).avisar(reg, Mock(), inicio-timedelta(minutes=30))
            self.assertEqual(path.read_text(), "{not json")

    def test_sem_quota_ou_volume_sem_consultas(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            self.assertEqual(VerificacaoOdds().avisar(reg, Mock(), inicio-timedelta(minutes=30)), 0)

    def test_alerta_metadata_nao_bloqueia_odds(self):
        modelo = {"casa":"Casa","fora":"Fora","liga":"Championship",
                  "timestamp":datetime(2030, 5, 10, 20, tzinfo=timezone.utc).timestamp()}
        fixture = {"id": "1", "casa":"Casa","fora":"Fora","liga":"Premier League",
                   "data":"2030-05-10T17:00:00Z"}
        self.assertEqual(set(AuditoriaOdds._alertas_contexto(modelo, fixture)),
                         {"horario_divergente", "competicao_divergente"})
        fixture["liga"]="EFL Championship"
        fixture["data"]="2030-05-10T20:00:00Z"
        self.assertEqual(AuditoriaOdds._alertas_contexto(modelo,fixture), [])

    def test_admin_commands_readonly_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg, inicio = self._previsoes(tmp)
            bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.previsoes=reg
            bot._auditoria_verificacao=VerificacaoOdds(Path(tmp)/"a.json")
            bot.odds=Mock()
            bot.odds._quota_local=GestorQuotaOdds(Path(tmp)/"quota.json")
            bot.odds.status_conta.return_value={
                "request_count":6, "request_limit":5000, "remaining":4994,
                "valid_until":"2030-06-13T00:00:00Z"
            }
            bot.username=None
            bot.owner_id=1
            bot.chat_id=1
            bot.enviar_mensagem=Mock()
            before=copy.deepcopy(reg.dados)
            bot.processar_comando(1, "/odds_verificacao", user_id=2)
            bot.enviar_mensagem.assert_not_called()
            bot.processar_comando(1, "/odds_verificacao", user_id=1)
            self.assertIn("VERIFICACAO ODDS", bot.enviar_mensagem.call_args.args[1])
            bot.processar_comando(1, "/quota_plano", user_id=1)
            self.assertIn("GESTAO QUOTA", bot.enviar_mensagem.call_args.args[1])
            self.assertEqual(reg.dados, before)


class QuotaPorOperacaoTests(unittest.TestCase):
    def test_contagem_por_dia_e_operacao_e_exclui_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            gest=GestorQuotaOdds(Path(tmp)/"pedidos.json")
            now=datetime(2030, 5, 10, 10, tzinfo=timezone.utc)
            gest.registar("/fixtures", "ODDS_AUTO", now)
            gest.registar("/odds", "CLV_AUTO", now)
            gest.registar("/odds", "CLV_AUTO", now)
            gest.registar("/account", "MANUAL", now)
            dados=GestorQuotaOdds(Path(tmp)/"pedidos.json").resumo(now)
            self.assertEqual(dados["total"], 3)
            self.assertEqual(dados["operacoes"]["CLV_AUTO"], 2)
            self.assertEqual(dados["endpoints"]["/odds"], 2)
            self.assertEqual(gest.resumo(now+timedelta(days=1))["total"], 0)

    def test_controlo_automatico_nao_bloqueia_clv_oficial(self):
        with tempfile.TemporaryDirectory() as tmp:
            gest=GestorQuotaOdds(Path(tmp)/"p.json")
            now=datetime(2030, 5, 10, 10, tzinfo=timezone.utc)
            status={"remaining":36, "request_count":100, "request_limit":136,
                    "valid_until":"2030-05-13T00:00:00Z"}
            limite=gest.plano(status,now)["objetivo_dia"]
            self.assertGreater(limite,0)
            for _ in range(limite):
                gest.registar("/fixtures", "ODDS_AUTO", now)
            self.assertFalse(gest.permite_extra(status, "ODDS_AUTO", now))
            self.assertFalse(gest.permite_extra(status, "CLV_TARDIO", now))
            self.assertTrue(gest.permite_extra(status, "CLV_AUTO", now))
            self.assertFalse(gest.permite_extra({**status,"remaining":20}, "ODDS_AUTO", now))

    def test_quota_official_provider_conta_so_pedidos_nao_account(self):
        class Resposta:
            status_code=200
            def raise_for_status(self):
                pass
            def json(self):
                return []
        with tempfile.TemporaryDirectory() as tmp:
            odds=OddsBetano(papi_key="teste",session=Mock(get=Mock(return_value=Resposta())))
            odds._quota_local=GestorQuotaOdds(Path(tmp)/"q.json")
            odds._esperar_cooldown_papi=Mock()
            odds._marcar_cooldown_papi=Mock()
            with odds.contexto_operacao("CLV_AUTO"):
                odds._get_papi("/fixtures", {"sportId":10})
            odds._get_papi("/account", {})
            dados=odds._quota_local.resumo()
            self.assertEqual(dados["total"],1)
            self.assertEqual(dados["operacoes"]["CLV_AUTO"],1)
            self.assertEqual(odds._operacao_odds,"MANUAL")

    def test_contador_corrompido_falha_sem_sobrescrever(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"p.json"
            path.write_text("{bug",encoding="utf-8")
            with self.assertRaises(RuntimeError):
                GestorQuotaOdds(path).registar("/fixtures")
            self.assertEqual(path.read_text(),"{bug")


if __name__=="__main__":
    unittest.main()
