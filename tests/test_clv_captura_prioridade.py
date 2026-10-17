"""Regressão offline: priorizar início do jogo no CLV sem ampliar quotas."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from main_sofascore import BotPremiumReal
from previsoes_premium import RegistoPrevisoes


TZ = ZoneInfo("Europe/Lisbon")


class CapturaCLVOrdemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg = RegistoPrevisoes(Path(self.tmp.name) / "previsoes.json")
        self.bot = BotPremiumReal.__new__(BotPremiumReal)
        self.bot.odds = SimpleNamespace(configurada=True)
        self.bot.previsoes = self.reg

    def snapshot(self, numero, inicio, *, fecho=None, estado="pendente"):
        p = {
            "event_id": numero,
            "data_jogo": inicio.strftime("%Y-%m-%d"),
            "timestamp_jogo": inicio.timestamp(),
            "estado": estado,
            "casa": f"Casa {numero}",
            "fora": f"Fora {numero}",
            "liga": "Teste",
            "mercado": "Under 2.5 Golos",
            "odd_valor_confirmado": 1.80,
            "odd_minima": 1.70,
            "probabilidade": 0.62,
            "qualidade": 80,
            "odd_justa": 1.61,
        }
        if fecho is not None:
            p["odd_fecho"] = fecho
        return p

    def candidatos(self, agora, tardio=False):
        with patch("main_sofascore.datetime") as tempo:
            tempo.now.return_value = agora
            return self.bot._selecoes_clv_proximas(tardio=tardio)

    def test_mais_urgente_primeiro_mesmo_se_snapshot_mais_recente(self):
        agora = datetime(2030, 6, 1, 18, 0, tzinfo=TZ)
        tardio = self.snapshot(10, agora + timedelta(minutes=27))
        urgente = self.snapshot(11, agora + timedelta(minutes=4))
        meio = self.snapshot(12, agora + timedelta(minutes=15))
        self.reg.dados["previsoes"] = [tardio, meio, urgente]
        original = copy.deepcopy(self.reg.dados)
        candidatos = self.candidatos(agora)
        self.assertEqual([s["jogo"]["id"] for s in candidatos], [11, 12, 10])
        self.assertEqual(original, self.reg.dados)

        # O fallback existente continua com o mesmo limite: 4 individuais.
        consulta = Mock(return_value=[])
        self.bot._enriquecer_com_cobertura = consulta
        self.bot._registar_tentativa_clv = Mock()
        self.assertEqual(self.bot._capturar_clv_pendentes(candidatos), 0)
        consulta.assert_called_once()
        self.assertEqual(consulta.call_args.kwargs["max_fallback_individual"], 4)
        self.assertEqual(
            [s["jogo"]["id"] for s in consulta.call_args.args[0]],
            [11, 12, 10],
        )
        self.assertEqual(original, self.reg.dados)

    def test_jogo_apos_meia_noite_e_elegivel_ainda_no_dia_anterior(self):
        agora = datetime(2030, 6, 1, 23, 45, tzinfo=TZ)
        proximo_dia = agora + timedelta(minutes=19)
        fora_janela = agora + timedelta(minutes=31)
        self.reg.dados["previsoes"] = [
            self.snapshot(2, fora_janela),
            self.snapshot(1, proximo_dia),
        ]
        candidatos = self.candidatos(agora)
        self.assertEqual([s["jogo"]["id"] for s in candidatos], [1])
        self.assertEqual(self.reg.dados["previsoes"][1]["data_jogo"], "2030-06-02")

    def test_nao_consulta_jogos_iniciados_fechados_ou_sem_value(self):
        agora = datetime(2030, 6, 1, 23, 50, tzinfo=TZ)
        valido = self.snapshot(1, agora + timedelta(minutes=8))
        iniciado = self.snapshot(2, agora - timedelta(seconds=2))
        fechado = self.snapshot(3, agora + timedelta(minutes=6), fecho=1.75)
        fechado["odd_fecho_tardio"] = 1.72
        sem_value = self.snapshot(4, agora + timedelta(minutes=7))
        sem_value["odd_valor_confirmado"] = None
        sem_value["odd_minima"] = 2.00
        passado = self.snapshot(5, agora + timedelta(minutes=7), estado="ganhou")
        self.reg.dados["previsoes"] = [passado, iniciado, fechado, valido, sem_value]
        self.assertEqual([s["jogo"]["id"] for s in self.candidatos(agora)], [1])
        self.assertEqual(self.candidatos(agora, tardio=True), [])

    def test_t10_tambem_fica_ordenado_mas_exige_fecho_existente(self):
        agora = datetime(2030, 6, 1, 23, 56, tzinfo=TZ)
        p1 = self.snapshot(10, agora + timedelta(minutes=9), fecho=1.70)
        p2 = self.snapshot(11, agora + timedelta(minutes=3), fecho=1.80)
        p3 = self.snapshot(12, agora + timedelta(minutes=2))
        self.reg.dados["previsoes"] = [p1, p2, p3]
        self.assertEqual([s["jogo"]["id"] for s in self.candidatos(agora, tardio=True)], [11, 10])
        self.assertEqual([s["jogo"]["id"] for s in self.candidatos(agora)], [12])

    def test_timestamp_nao_finito_e_excluido(self):
        agora = datetime(2030, 6, 1, 18, 0, tzinfo=TZ)
        n = self.snapshot(10, agora + timedelta(minutes=4))
        n["timestamp_jogo"] = float("nan")
        i = self.snapshot(11, agora + timedelta(minutes=4))
        i["timestamp_jogo"] = float("inf")
        valid = self.snapshot(12, agora + timedelta(minutes=5))
        self.reg.dados["previsoes"] = [n, i, valid]
        self.assertEqual([s["jogo"]["id"] for s in self.candidatos(agora)], [12])


if __name__ == "__main__":
    unittest.main()
