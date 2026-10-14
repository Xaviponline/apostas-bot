"""Rotinas automaticas: janelas off-CLV, idempotencia e relatorio OWNER."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from rotinas_diarias import RotinasDiarias


TZ = ZoneInfo("Europe/Lisbon")
INICIO = datetime(2026, 10, 13, 19, 45, tzinfo=TZ)


def agora(d=14, h=2, m=10):
    return datetime(2026, 10, d, h, m, tzinfo=TZ)


class FakePrevisoes:
    def __init__(self, pendentes=1):
        self.dados = {
            "previsoes": [
                {
                    "estado": "pendente",
                    "timestamp_jogo": INICIO.timestamp(),
                    "data_jogo": "2026-10-13",
                    "casa": "A",
                    "fora": "B",
                    "mercado": "Under 2.5 Golos",
                    "probabilidade": 0.65,
                    "odd_real": 1.88,
                    "ranking_modelo": 1,
                    "resultado_binario": None,
                }
                for _ in range(pendentes)
            ]
        }
        self.atualizar_pendentes = Mock(return_value=0)

    def metricas_v13_comercial(self):
        return {
            "coorte_tamanho": 6, "alvo": 50, "liquidadas": 3,
            "pendentes": 3, "dias": 3, "min_dias": 20,
            "clv_amostras": 4, "min_clv_amostras": 40,
            "ganhos": 1, "perdas": 2,
            "lucro_unidades": -1.25, "roi": -1.25 / 3,
            "clv_media": 0.001,
        }


class LiquidacaoAutomaticaTests(unittest.TestCase):
    def test_antes_de_tres_horas_nao_aciona_espn(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            p.dados["previsoes"][0]["timestamp_jogo"] = datetime(2026, 10, 14, 0, 0, tzinfo=TZ).timestamp()
            r = RotinasDiarias(Path(td) / "rotinas.json")
            self.assertEqual(r.liquidar_se_devido(p, agora(h=1)), 0)
            p.atualizar_pendentes.assert_not_called()

    def test_janela_madrugada_e_sem_odds(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            r = RotinasDiarias(Path(td) / "rotinas.json")
            self.assertEqual(r.liquidar_se_devido(p, agora()), 0)
            p.atualizar_pendentes.assert_called_once()
            estado = json.loads((Path(td) / "rotinas.json").read_text())
            self.assertEqual(estado["ultimo_total_liquidado"], 0)
            self.assertEqual(estado["ultima_liquidacao_tentada"][:10], "2026-10-14")

    def test_intervalo_duas_horas_persiste_apos_reinicio(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            path = Path(td) / "rotinas.json"
            RotinasDiarias(path).liquidar_se_devido(p, agora())
            RotinasDiarias(path).liquidar_se_devido(p, agora(h=3))
            self.assertEqual(p.atualizar_pendentes.call_count, 1)
            RotinasDiarias(path).liquidar_se_devido(p, agora(h=4, m=11))
            self.assertEqual(p.atualizar_pendentes.call_count, 2)

    def test_sem_capturas_entre_15h30_e_00h45(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            r = RotinasDiarias(Path(td) / "rotinas.json")
            for t in (agora(h=15, m=30), agora(h=18), agora(h=19, m=15), agora(h=23, m=59)):
                self.assertEqual(r.liquidar_se_devido(p, t), 0)
            p.atualizar_pendentes.assert_not_called()

    def test_espn_nao_e_chamada_com_tudo_liquidado(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes(pendentes=0)
            self.assertEqual(RotinasDiarias(Path(td) / "rotinas.json").liquidar_se_devido(p, agora()), 0)
            p.atualizar_pendentes.assert_not_called()

    def test_erro_espn_preserva_intervalo_para_evitar_loop(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            p.atualizar_pendentes.side_effect = RuntimeError("ESPN sem resposta")
            path = Path(td) / "rotinas.json"
            r = RotinasDiarias(path)
            with self.assertRaises(RuntimeError):
                r.liquidar_se_devido(p, agora())
            self.assertEqual(r.liquidar_se_devido(p, agora(h=3)), 0)
            p.atualizar_pendentes.assert_called_once()
            estado = json.loads(path.read_text())
            self.assertNotIn("ultima_liquidacao_concluida", estado)

    def test_marcador_corrompido_falha_fechado(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rotinas.json"
            path.write_text("{" + "invalido", encoding="utf-8")
            p = FakePrevisoes()
            with self.assertRaises(RuntimeError):
                RotinasDiarias(path).liquidar_se_devido(p, agora())
            p.atualizar_pendentes.assert_not_called()
            self.assertEqual(path.read_text(), "{invalido")

    def test_maturidade_em_horario_inverno(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            p.dados["previsoes"][0]["timestamp_jogo"] = datetime(2026, 11, 13, 23, tzinfo=TZ).timestamp()
            r = RotinasDiarias(Path(td) / "rotinas.json")
            self.assertEqual(r.liquidar_se_devido(p, datetime(2026, 11, 14, 1, 0, tzinfo=TZ)), 0)
            self.assertEqual(r.liquidar_se_devido(p, datetime(2026, 11, 14, 3, 0, tzinfo=TZ)), 0)
            p.atualizar_pendentes.assert_called_once()


class ResumoAutomTests(unittest.TestCase):
    def test_resumo_diario_apenas_ontem_e_progressao_v13_separados(self):
        p = FakePrevisoes()
        p.dados["previsoes"] += [
            {"data_jogo": "2026-10-13", "estado": "ganhou", "resultado_binario": 1},
            {"data_jogo": "2026-10-13", "estado": "perdeu", "resultado_binario": 0},
            {"data_jogo": "2026-10-12", "estado": "ganhou", "resultado_binario": 1},
        ]
        texto = RotinasDiarias.texto_resumo(p, agora(h=10, m=40))
        self.assertIn("Registadas: 3", texto)
        self.assertIn("Liquidadas: 2 | Pendentes: 1", texto)
        self.assertIn("Entradas: 6/50", texto)
        self.assertIn("CLV: 4/40 minimo", texto)
        self.assertIn("ROI: -41,7%", texto)
        self.assertIn("previsao(oes)", texto)

    def test_envio_uma_vez_por_dia_mesmo_apos_restart(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            path = Path(td) / "rotinas.json"
            enviar = Mock()
            self.assertFalse(RotinasDiarias(path).enviar_relatorio_se_devido(p, enviar, agora(h=10, m=29)))
            self.assertTrue(RotinasDiarias(path).enviar_relatorio_se_devido(p, enviar, agora(h=10, m=30)))
            self.assertFalse(RotinasDiarias(path).enviar_relatorio_se_devido(p, enviar, agora(h=14)))
            self.assertFalse(RotinasDiarias(path).enviar_relatorio_se_devido(p, enviar, agora(h=20)))
            enviar.assert_called_once()
            self.assertEqual(json.loads(path.read_text())["ultimo_relatorio_enviado"], "2026-10-14")

    def test_novo_dia_novo_resumo(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            r = RotinasDiarias(Path(td) / "rotinas.json")
            enviar = Mock()
            self.assertTrue(r.enviar_relatorio_se_devido(p, enviar, agora(h=11)))
            self.assertTrue(r.enviar_relatorio_se_devido(p, enviar, agora(d=15, h=11)))
            self.assertEqual(enviar.call_count, 2)

    def test_nao_grava_sucesso_se_telegram_falhou(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            path = Path(td) / "rotinas.json"
            r = RotinasDiarias(path)
            enviar = Mock(side_effect=RuntimeError("Telegram recusou"))
            with self.assertRaises(RuntimeError):
                r.enviar_relatorio_se_devido(p, enviar, agora(h=11))
            self.assertFalse(path.exists())
            self.assertTrue(r.enviar_relatorio_se_devido(p, Mock(), agora(h=11, m=3)))

    def test_status_read_only_e_sem_rede(self):
        with tempfile.TemporaryDirectory() as td:
            p = FakePrevisoes()
            path = Path(td) / "rotinas.json"
            r = RotinasDiarias(path)
            msg = r.relatorio_estado(p, agora(h=11))
            self.assertIn("ROTINAS DIARIAS", msg)
            self.assertIn("Pendentes maduros neste instante: 1", msg)
            self.assertFalse(path.exists())
            p.atualizar_pendentes.assert_not_called()

    def test_so_owner_vê_comando(self):
        with tempfile.TemporaryDirectory() as td:
            bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
            bot.username = None
            bot.owner_id = 123
            bot.chat_id = 123
            bot.enviar_mensagem = Mock()
            bot.previsoes = FakePrevisoes()
            bot._rotinas_diarias = RotinasDiarias(Path(td) / "rotinas.json")
            bot.processar_comando(123, "/rotinas_status", user_id=999)
            bot.processar_comando(456, "/rotinas_status", user_id=123)
            bot.enviar_mensagem.assert_not_called()
            bot.processar_comando(123, "/rotinas_status", user_id=123)
            bot.enviar_mensagem.assert_called_once()
            self.assertIn("ROTINAS DIARIAS", bot.enviar_mensagem.call_args.args[1])

    def test_excecao_espn_nao_impede_relatorio_e_v13(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot._rotinas_diarias = Mock()
        bot._rotinas_diarias.liquidar_se_devido.side_effect = RuntimeError("falha ESPN")
        bot.owner_id = 123
        bot.chat_id = 123
        bot.previsoes = FakePrevisoes()
        bot.enviar_mensagem = Mock()
        bot._rotinas_diarias_se_devido()
        bot._rotinas_diarias.enviar_relatorio_se_devido.assert_called_once()


if __name__ == "__main__":
    unittest.main()
