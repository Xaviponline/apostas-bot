"""Regressões de produção Lambda Shadow: não alterar seleções nem consultar APIs."""
import unittest
from types import SimpleNamespace
from analisador_inteligente import AnalisadorInteligente
from estatisticas_espn import EstatisticasESPN
from lambda_prospectivo_shadow import criar_registo
from main_sofascore import BotPremiumReal


class EstatisticasFalsas:
    def __init__(self, analise, partidas):
        self.analise = analise
        self.partidas = partidas

    def resolver_liga(self, jogo):
        return "uefa.europa.conf"

    def carregar_historicos(self, jogos):
        return {"uefa.europa.conf": self.partidas}

    def analisar_jogo(self, jogo, partidas):
        return self.analise


class TestLambdaIntegracaoProducao(unittest.TestCase):
    def _executar(self, extra=None):
        jogo = dict(id=11, casa_id=22, fora_id=33, timestamp=1900000000,
                    liga_codigo="uefa.europa.conf")
        analise = dict(jogo=jogo, liga_codigo="uefa.europa.conf",
                       lambda_casa=1.5, lambda_fora=1.0,
                       probabilidades=EstatisticasESPN._probabilidades(1.5, 1.0),
                       forma_fonte="multicompeticao")
        analise.update(extra or {})
        partidas = [dict(golos_casa=2, golos_fora=0),
                    dict(golos_casa=1, golos_fora=2)]
        analisador = AnalisadorInteligente(
            estatisticas=EstatisticasFalsas(analise, partidas))
        vistas_oficiais = []
        analisador._melhor_selecao = lambda a: vistas_oficiais.append(a) or None
        self.assertEqual(analisador.gerar_todas_apostas([jogo]), [])
        self.assertIs(vistas_oficiais[0], analise)
        self.assertNotIn("media_liga_casa", analise)
        self.assertNotIn("media_liga_fora", analise)
        return analisador.ultimas_analises_shadow[0]

    def test_multicompeticao_recupera_medias_so_para_shadow(self):
        shadow = self._executar()
        self.assertEqual(shadow["media_liga_casa"], 1.5)
        self.assertEqual(shadow["media_liga_fora"], 1.0)
        self.assertIsNotNone(criar_registo(shadow))

    def test_competicao_neutra_usa_baseline_simetrico(self):
        shadow = self._executar({"contexto_partida": "neutro",
                                "baseline_neutro": 1.25})
        self.assertEqual(shadow["media_liga_casa"], 1.25)
        self.assertEqual(shadow["media_liga_fora"], 1.25)
        self.assertIsNotNone(criar_registo(shadow))

    def test_analise_diaria_invoca_resultados_independentes(self):
        eventos = []
        class Agenda:
            def executar_se_devido(self, acao, agora=None):
                acao()
                return True
        bot = BotPremiumReal.__new__(BotPremiumReal)
        bot.previsoes = SimpleNamespace(dados={"previsoes": []})
        bot._agenda_analise_diaria = Agenda()
        bot._executar_analise = lambda tecnica=False: eventos.append("analise")
        bot._guardar_lambda_auto = lambda: eventos.append("snapshots")
        bot._guardar_lambda_resultados_auto = lambda: eventos.append("resultados")
        self.assertTrue(bot._executar_analise_auto_se_devida())
        self.assertEqual(eventos, ["analise", "snapshots", "resultados"])


if __name__ == "__main__":
    unittest.main()
