"""PR #69 — provas offline da auditoria estatística exclusivamente SHADOW."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from main_competicoes import BotPremiumDiarioCompeticoes
from v13_robustez_shadow import relatorio_robustez_v13


def metricas(coorte, estado="RECOLHA", alvo=50):
    liquidadas = [p for p in coorte if p.get("resultado_binario") in (0, 1)]
    return {
        "coorte": copy.deepcopy(coorte),
        "coorte_tamanho": len(coorte),
        "alvo": alvo,
        "estado": estado,
        "clv_amostras": 0,
        "max_drawdown": 0.0,
        "max_streak_perdas": 0,
        "liquidadas": len(liquidadas),
    }


def entrada(n, data, ganhou=True, mercado="Ambas Marcam"):
    return {
        "snapshot": n,
        "data_jogo": data,
        "mercado": mercado,
        "resultado_binario": int(ganhou) if ganhou is not None else None,
        "lucro_unidades": (0.80 if ganhou else -1.0) if ganhou is not None else None,
        "odd_entrada": 1.80,
        "odd_fecho": None,
    }


class RobustezV13ShadowTests(unittest.TestCase):
    def test_zero_liquidadas_nao_inventa_roi(self):
        dados = metricas([entrada(207, "2026-10-16", None)])
        antes = copy.deepcopy(dados)
        texto = relatorio_robustez_v13(dados)
        self.assertIn("Sem entradas VALUE liquidadas", texto)
        self.assertNotIn("IC95%", texto)
        self.assertEqual(dados, antes)

    def test_coorte_parcial_e_pendentes_excluidas_e_gate_inalterado(self):
        dados = metricas([
            entrada(207, "2026-10-16", True),
            entrada(208, "2026-10-16", False),
            entrada(209, "2026-10-17", None),
        ])
        antes = copy.deepcopy(dados)
        texto = relatorio_robustez_v13(dados)
        self.assertIn("Liquidadas: 2", texto)
        self.assertIn("Intervalo não estimado", texto)
        self.assertIn("Estado do gate original: RECOLHA", texto)
        self.assertNotIn("IC95% bootstrap", texto)
        self.assertEqual(dados, antes)

    def test_uma_unica_data_nao_permite_inferencia_mesmo_com_20(self):
        dados = metricas([
            entrada(207 + k, "2030-01-01", True) for k in range(20)
        ])
        texto = relatorio_robustez_v13(dados)
        self.assertIn("20 liquidadas, 1 dias", texto)
        self.assertNotIn("IC95% bootstrap", texto)

    def test_bootstrap_por_dia_deterministico_e_nao_decide_gate(self):
        origem = datetime(2030, 1, 1, tzinfo=timezone.utc)
        c = [
            entrada(207 + k, (origem + timedelta(days=k // 2)).date().isoformat())
            for k in range(20)
        ]
        dados = metricas(c, estado="PASSOU")
        original = copy.deepcopy(dados)
        a = relatorio_robustez_v13(dados)
        b = relatorio_robustez_v13(dados)
        self.assertEqual(a, b)
        self.assertIn("IC95% bootstrap por dia: +80,0% a +80,0%", a)
        self.assertIn("validação adicional ainda obrigatória", a)
        self.assertIn("Estado do gate original: PASSOU (inalterado)", a)
        self.assertEqual(dados, original)

    def test_lucro_negativo_e_mercados_frequentes(self):
        inicio = datetime(2030, 1, 1, tzinfo=timezone.utc)
        dados = metricas([
            entrada(207 + k, (inicio + timedelta(days=k)).date().isoformat(), False, "Under 2.5 Golos")
            for k in range(21)
        ])
        s = relatorio_robustez_v13(dados)
        self.assertIn("Mercado mais frequente: Under 2.5 Golos — 21/21", s)
        self.assertIn("IC95% bootstrap por dia: -100,0% a -100,0%", s)
        self.assertIn("Intervalo abaixo de ROI 0%", s)

    def test_dados_corrompidos_falham_fechado(self):
        p = entrada(207, "2030-01-01")
        p["lucro_unidades"] = float("nan")
        with self.assertRaises(ValueError):
            relatorio_robustez_v13(metricas([p]))
        p["lucro_unidades"] = 0.8
        p["data_jogo"] = ""
        texto = relatorio_robustez_v13(metricas([p]))
        self.assertIn("datas inválidas", texto)

    def test_comando_somente_owner_sem_odds_ou_mutacoes(self):
        dados = metricas([entrada(207, "2026-10-16", True)])
        antes = copy.deepcopy(dados)
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id, bot.chat_id, bot.username = 51, 51, None

        class PrevisoesFake:
            def metricas_v13_comercial(self):
                return dados

        bot.previsoes = PrevisoesFake()
        enviados = []
        bot.enviar_mensagem = lambda cid, texto: enviados.append((cid, texto))
        bot.processar_comando(52, "/v13_robustez", user_id=52)
        self.assertEqual(enviados, [])
        bot.processar_comando(51, "/v13_robustez", user_id=51)
        self.assertEqual(len(enviados), 1)
        self.assertIn("V1.3 ROBUSTEZ", enviados[0][1])
        self.assertEqual(dados, antes)


if __name__ == "__main__":
    unittest.main()
