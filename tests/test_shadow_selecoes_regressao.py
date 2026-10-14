"""Testes sem rede dos filtros V1.2 no replay SHADOW e de ligas regulares.

Fixtures artificiais, não picks. Nenhuma escrita, odds externas ou snapshots.
"""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from analisador_inteligente import AnalisadorInteligente
from estatisticas_espn import EstatisticasESPN
from estatisticas_hibridas_competicoes import EstatisticasHibridasCompeticoes
from scripts.comparar_cobertura_shadow import avaliar_filtros_shadow


def analise(codigo, prob, qualidade=80):
    return {
        "jogo": {"league_code": codigo, "casa": "Equipa X", "fora": "Equipa Y"},
        "liga_codigo": codigo,
        "qualidade": qualidade,
        "probabilidades": {"Under 3.5 Golos": prob},
    }


class ReplaySelecoesShadowTests(unittest.TestCase):
    def test_mesmos_filtros_da_v12_sem_modificar_analises(self):
        motor = AnalisadorInteligente()
        entradas = [
            ("uefa.champions", analise("uefa.champions", 0.74)),
            ("uefa.champions", analise("uefa.champions", 0.74, 54)),
            ("por.taca.portugal", analise("por.taca.portugal", 0.55)),
        ]
        copia = copy.deepcopy(entradas)
        resumo = avaliar_filtros_shadow(entradas, motor)
        self.assertEqual(entradas, copia)
        self.assertEqual(resumo["analisados"]["uefa.champions"], 2)
        self.assertEqual(resumo["sem_qualidade"]["uefa.champions"], 1)
        self.assertEqual(resumo["sem_mercado"]["por.taca.portugal"], 1)
        self.assertEqual(resumo["elegiveis"]["uefa.champions"], 1)
        self.assertEqual(resumo["top5_local"]["uefa.champions"], 1)
        self.assertEqual(resumo["total_elegiveis"], 1)
        self.assertFalse(resumo["value_confirmado"])
        self.assertFalse(resumo["ranking_global_confirmado"])

    def test_top5_e_limite_locais_usam_mesma_ordenacao_da_cobertura(self):
        entradas = [
            ("uefa.champions", analise("uefa.champions", p))
            for p in [0.75, 0.749, 0.74, 0.73, 0.72, 0.71, 0.70]
        ]
        resumo = avaliar_filtros_shadow(entradas)
        self.assertEqual(resumo["total_elegiveis"], 7)
        self.assertEqual(resumo["top5_local"]["uefa.champions"], 5)
        self.assertEqual(resumo["dentro_limite_local"]["uefa.champions"], 7)
        self.assertNotIn("ranking_modelo", entradas[0][1])

    def test_odds_de_mercado_ausentes_nao_criam_value(self):
        entradas = [("uefa.champions", analise("uefa.champions", 0.75))]
        resultado = avaliar_filtros_shadow(entradas)
        self.assertEqual(resultado["total_elegiveis"], 1)
        self.assertFalse(resultado["value_confirmado"])
        self.assertNotIn("odd_real", entradas[0][1])
        self.assertEqual(AnalisadorInteligente.MARGEM_VALUE_ALVO, 0.05)
        self.assertEqual(AnalisadorInteligente.QUALIDADE_MINIMA, 55)
        self.assertEqual(AnalisadorInteligente.ODD_MINIMA_PERFIL, 1.50)


class RegressaoLigasRegularesTests(unittest.TestCase):
    def test_probabilidades_e_qualidade_identicas_na_liga_regular(self):
        ref = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("Europe/Lisbon"))
        partidas = [
            {
                "id": i + 1, "liga_codigo": "eng.2",
                "timestamp": ref.timestamp() - (i + 1) * 86400,
                "casa_id": 101 if i % 2 == 0 else 303,
                "fora_id": 202 if i % 2 == 0 else 404,
                "golos_casa": 1 + i % 3,
                "golos_fora": i % 2,
            }
            for i in range(40)
        ]
        jogo = {"league_code": "eng.2", "liga": "English League Championship", "casa_id": 101, "fora_id": 202}
        original = EstatisticasESPN().analisar_jogo(jogo, partidas)
        hibrido = EstatisticasHibridasCompeticoes().analisar_jogo(jogo, partidas)
        self.assertIsNotNone(original)
        self.assertIsNotNone(hibrido)
        for campo in (
            "qualidade", "probabilidades", "lambda_casa", "lambda_fora",
            "amostra_casa", "amostra_fora", "amostra_liga",
        ):
            self.assertEqual(original[campo], hibrido[campo], campo)
        self.assertEqual(
            AnalisadorInteligente()._melhor_selecao(original),
            AnalisadorInteligente()._melhor_selecao(hibrido),
        )


if __name__ == "__main__":
    unittest.main()
