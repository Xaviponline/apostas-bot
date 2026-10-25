"""Auditoria SHADOW: casos de regressao de selecao/odds, sem APIs ou escrita.

Executar na raiz do repositorio:
  python -m unittest discover -s tests -p 'test_seguranca_mercados_shadow_20261025.py' -v

Os @expectedFailure documentam fragilidades atuais: nao sao correcoes.
Nao fazer merge/deploy enquanto houver regressões conhecidas.
"""
import copy
import unittest

from analisador_inteligente import AnalisadorInteligente
from estatisticas_espn import EstatisticasESPN
from odds_auditoria import AuditoriaOdds


def payload_totais(*, handicap=None, selecoes=None, nome="Total Goals"):
    mercado = {
        "name": nome,
        "period": "fulltime",
        "odds": selecoes or [{"seleção": "Under 2.5", "odd": 1.90}],
    }
    if handicap is not None:
        mercado["handicap"] = handicap
    return {"casa": "Clube A", "fora": "Clube B", "mercados": [mercado]}


class TestCorrespondenciaDeLinhasShadow(unittest.TestCase):
    def test_linha_explicita_e_selecao_corretas(self):
        dados = payload_totais(
            handicap=2.5, selecoes=[{"seleção": "Under", "odd": 1.91}]
        )
        self.assertEqual(
            AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"), (1.91, "")
        )

    def test_linha_explicita_diferente_e_rejeitada(self):
        dados = payload_totais(
            handicap=3.5, selecoes=[{"seleção": "Under", "odd": 1.25}]
        )
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"))

    def test_periodo_primeira_parte_e_rejeitado(self):
        dados = payload_totais(
            handicap=2.5, selecoes=[{"seleção": "Under", "odd": 1.45}]
        )
        dados["mercados"][0]["period"] = "firsthalf"
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"))

    def test_multiplas_linhas_indistintas_sao_rejeitadas(self):
        dados = payload_totais(selecoes=[
            {"seleção": "Under 2.5", "odd": 1.88},
            {"seleção": "Under 2.5", "odd": 1.91},
        ])
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"))

    def test_leitura_nao_modifica_payload(self):
        dados = payload_totais(
            handicap=2.5, selecoes=[{"seleção": "Under", "odd": 1.75}]
        )
        original = copy.deepcopy(dados)
        AuditoriaOdds._extrair_odd_diagnostico(dados, "Under 2.5 Golos")
        self.assertEqual(dados, original)

    @unittest.expectedFailure
    def test_regressao_nao_confundir_under_12_5_com_under_2_5(self):
        """BUG CONHECIDO: fallback textual usa substring sem fronteira numerica."""
        dados = payload_totais(selecoes=[
            {"seleção": "Under 12.5", "odd": 1.10}
        ])
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"))

    @unittest.expectedFailure
    def test_regressao_nao_confundir_linha_do_nome_12_5_com_2_5(self):
        """BUG CONHECIDO: substring no nome pode identificar linha incorreta."""
        dados = payload_totais(
            nome="Total Goals 12.5",
            selecoes=[{"seleção": "Under", "odd": 1.12}],
        )
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"))

    @unittest.expectedFailure
    def test_regressao_handicap_2_5_com_selecao_under_3_5_contraditoria(self):
        """BUG CONHECIDO: handicap sobrepoe-se a selecao textual contraditoria."""
        dados = payload_totais(
            handicap=2.5,
            selecoes=[{"seleção": "Under 3.5", "odd": 1.55}],
        )
        self.assertIsNone(AuditoriaOdds._extrair_odd(dados, "Under 2.5 Golos"))


class TestSelecaoModeloShadow(unittest.TestCase):
    def test_ranking_usa_probabilidade_e_nao_odds(self):
        analisador = AnalisadorInteligente()
        analise = {
            "qualidade": 90,
            "probabilidades": {"Ambas Marcam": 0.668, "Over 2.5 Golos": 0.66},
            "odds_exemplo": {"Ambas Marcam": 1.60, "Over 2.5 Golos": 1.80},
        }
        escolhida = analisador._melhor_selecao(analise)
        self.assertEqual(escolhida["mercado"], "Ambas Marcam")
        p_ambas = analisador._probabilidade_conservadora(0.668, 90)
        p_over = analisador._probabilidade_conservadora(0.66, 90)
        self.assertLess(1.60, 1.05 / p_ambas)
        self.assertGreaterEqual(1.80, 1.05 / p_over)

    def test_limite_implicito_70_porcento(self):
        analisador = AnalisadorInteligente()
        demasiado_alta = {
            "qualidade": 90, "probabilidades": {"Under 3.5 Golos": 0.8}
        }
        no_limite = {
            "qualidade": 90, "probabilidades": {"Under 3.5 Golos": 0.75}
        }
        self.assertIsNone(analisador._melhor_selecao(demasiado_alta))
        self.assertAlmostEqual(
            analisador._melhor_selecao(no_limite)["probabilidade"], 0.70
        )

    def test_qualidade_e_filtro_nao_peso_da_probabilidade(self):
        modelo = AnalisadorInteligente()
        p_baixa = modelo._probabilidade_conservadora(0.72, 55)
        p_alta = modelo._probabilidade_conservadora(0.72, 100)
        self.assertEqual(p_baixa, p_alta)

    def test_complementaridade_under_over_no_poisson(self):
        raw = EstatisticasESPN._probabilidades(1.4, 1.2)
        self.assertAlmostEqual(
            raw["Under 2.5 Golos"] + raw["Over 2.5 Golos"], 1.0, places=12
        )
        self.assertAlmostEqual(
            raw["Under 3.5 Golos"] + raw["Over 3.5 Golos"], 1.0, places=12
        )


if __name__ == "__main__":
    unittest.main()
