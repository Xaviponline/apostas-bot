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
