import unittest
from datetime import datetime

from main_diario import TZ_PORTUGAL
from main_enriquecido import BotPremiumDiarioDiagnostico, BuscadorJogosEnriquecido


class EstatisticasCoberturaFake:
    ultimo_erros = {}

    @staticmethod
    def resolver_liga(jogo):
        codigo = jogo.get("league_code")
        return codigo if codigo in {"esp.1"} else None

    def carregar_historicos(self, jogos, data_ref=None):
        return {"esp.1": [object()]}

    def analisar_jogo(self, jogo, partidas):
        if jogo.get("sem_dados"):
            return None
        return {
            "jogo": jogo,
            "qualidade": 80,
            "passa": bool(jogo.get("passa")),
        }


class EstatisticasCoberturaSemSuporteFake:
    def __init__(self):
        self.ultimo_erros = {"uefa.nations": "HTTP 403"}
        self._formas_globais = {123: [1, 2, 3, 4]}
        self.ultimo_erros_forma = {456: "HTTP 403"}
        self.diagnostico_base = {
            "uefa.nations": {"fonte": "sofascore_indisponivel", "jogos": 0}
        }
        self.diagnostico_forma_global = {123: {"jogos": 4}}
        self.chamadas = 0

    @staticmethod
    def resolver_liga(jogo):
        return None

    def carregar_historicos(self, jogos, data_ref=None):
        self.chamadas += 1
        self.ultimo_erros = {}
        self._formas_globais = {}
        self.ultimo_erros_forma = {}
        return {}


class AnalisadorCoberturaSemSuporteFake:
    MAX_SELECOES = 20

    def __init__(self):
        self.estatisticas = EstatisticasCoberturaSemSuporteFake()

    @staticmethod
    def _bandeira_liga(liga):
        return "🌍"

    @staticmethod
    def _melhor_selecao(analise):
        return None


class AnalisadorCoberturaFake:
    MAX_SELECOES = 15

    def __init__(self):
        self.estatisticas = EstatisticasCoberturaFake()

    @staticmethod
    def _bandeira_liga(liga):
        return "🇪🇸" if "LaLiga" in str(liga) else "🌍"

    @staticmethod
    def _melhor_selecao(analise):
        if not analise.get("passa"):
            return None
        return {"score": 0.80, "qualidade": 80}




class BuscadorVazioFake:
    estado = "operacional"
    fonte = "ESPN"
    espn_http_status = 200
    sofa_http_status = None


class CoberturaCommandTests(unittest.TestCase):
    def test_mapa_producao_inclui_novas_ligas(self):
        esperados = {
            "eng.2", "eng.3", "eng.4", "esp.2", "ita.2", "ger.2",
            "sco.1", "sco.2", "aut.1", "den.1", "gre.1", "sui.1",
        }
        self.assertTrue(esperados.issubset(BuscadorJogosEnriquecido.ESPN_CODIGO_NOME))

    def test_cobertura_mostra_cobertura_dados_e_selecao(self):
        futuro = datetime.now(TZ_PORTUGAL).timestamp() + 3600
        jogos = [
            {
                "id": 1,
                "liga": "Spanish LaLiga",
                "league_code": "esp.1",
                "timestamp": futuro,
                "passa": True,
            },
            {
                "id": 2,
                "liga": "Spanish LaLiga",
                "league_code": "esp.1",
                "timestamp": futuro + 60,
                "sem_dados": True,
            },
            {
                "id": 3,
                "liga": "Taça não suportada",
                "timestamp": futuro + 120,
            },
        ]
        bot = object.__new__(BotPremiumDiarioDiagnostico)
        bot.analisador = AnalisadorCoberturaFake()
        bot._jogos_hoje_portugal = lambda: jogos

        texto = bot._executar_cobertura()

        self.assertIn("COBERTURA V1", texto)
        self.assertIn("LaLiga: 2 → 2 → 1 → 1", texto)
        self.assertIn("Taça não suportada: 1 → 0 → 0 → 0", texto)
        self.assertIn("Dentro da cobertura: 2", texto)
        self.assertIn("Fora: 1", texto)
        self.assertIn("Seleção atual: 1/15 máximo", texto)

    def test_cobertura_sem_suporte_limpa_diagnosticos_da_execucao_anterior(self):
        futuro = datetime.now(TZ_PORTUGAL).timestamp() + 3600
        jogos = [
            {
                "id": 99,
                "liga": "League Phase",
                "timestamp": futuro,
            }
        ]
        bot = object.__new__(BotPremiumDiarioDiagnostico)
        bot.analisador = AnalisadorCoberturaSemSuporteFake()
        bot._jogos_hoje_portugal = lambda: jogos

        texto = bot._executar_cobertura()
        stats = bot.analisador.estatisticas

        self.assertIn("Dentro da cobertura: 0", texto)
        self.assertEqual(stats.chamadas, 1)
        self.assertEqual(stats.ultimo_erros, {})
        self.assertEqual(stats._formas_globais, {})
        self.assertEqual(stats.ultimo_erros_forma, {})
        self.assertEqual(stats.diagnostico_base, {})
        self.assertEqual(stats.diagnostico_forma_global, {})

    def test_cobertura_zero_expoe_diagnostico_da_fonte(self):
        bot = object.__new__(BotPremiumDiarioDiagnostico)
        bot.analisador = AnalisadorCoberturaFake()
        bot.buscador = BuscadorVazioFake()
        bot._jogos_hoje_portugal = lambda: []

        texto = bot._executar_cobertura()

        self.assertIn("listagem de jogos veio vazia", texto)
        self.assertIn("estado operacional", texto)
        self.assertIn("fonte ESPN", texto)
        self.assertIn("ESPN HTTP 200", texto)
        self.assertIn("Limite configurado: 15 seleções", texto)


if __name__ == "__main__":
    unittest.main()
