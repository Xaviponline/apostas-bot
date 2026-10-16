"""Regressões do /estudo_jogo: transparência, acesso e imutabilidade."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from estudo_jogo_shadow import gerar_estudo_jogo
from main_competicoes import BotPremiumDiarioCompeticoes


TZ_PT = ZoneInfo("Europe/Lisbon")


def snapshot(data=None, ranking=1, diag=True, mercado="Over 2.5 Golos"):
    inicio = data or datetime(2030, 10, 16, 20, 0, tzinfo=TZ_PT)
    s = {
        "chave": f"2030-evento-{ranking}|{mercado}",
        "event_id": ranking,
        "data_jogo": inicio.date().isoformat(),
        "timestamp_jogo": inicio.timestamp(),
        "casa": f"Casa {ranking}",
        "fora": f"Fora {ranking}",
        "liga": "Liga Teste",
        "ranking_modelo": ranking,
        "confianca_modelo": "ALTA",
        "mercado": mercado,
        "modelo_versao": "V1.2",
        "estado": "pendente",
        "probabilidade": 0.675,
        "probabilidade_bruta": 0.71875,
        "qualidade": 86,
        "odd_minima": 1.56,
        "odd_real": 1.65,
    }
    if diag:
        s["diagnostico_modelo"] = {
            "lambda_casa": 1.9, "lambda_fora": 1.2,
            "ppg_casa": 1.83, "ppg_fora": 1.5,
            "amostra_casa": 8, "amostra_fora": 8,
            "amostra_casa_local": 5, "amostra_fora_local": 4,
            "amostra_liga": 27,
            "media_liga_casa": 1.6, "media_liga_fora": 1.1,
            "probabilidades_brutas_mercados": {
                "Over 2.5 Golos": 0.67, "Ambas Marcam": 0.59,
                "Under 3.5 Golos": 0.60, "Vitória Casa": 0.52,
            },
        }
    return s


class EstudoJogoShadowTests(unittest.TestCase):
    def setUp(self):
        self.agora = datetime(2030, 10, 16, 10, 0, tzinfo=TZ_PT)

    def test_lista_usa_so_jogos_do_dia_ranking_ordenado(self):
        ps = [
            snapshot(ranking=3), snapshot(ranking=1),
            snapshot(datetime(2030, 10, 17, 21, tzinfo=TZ_PT), ranking=2),
        ]
        antes = copy.deepcopy(ps)
        texto = gerar_estudo_jogo(ps, "", agora=self.agora)
        self.assertIn("2 previsões disponíveis", texto)
        self.assertLess(texto.index("#1 ·"), texto.index("#3 ·"))
        self.assertNotIn("Casa 2", texto)
        self.assertEqual(ps, antes)

    def test_estudo_exibe_dados_congelados_e_limites(self):
        ps = [snapshot()]
        antes = copy.deepcopy(ps)
        texto = gerar_estudo_jogo(ps, "1", agora=self.agora)
        self.assertIn("Casa 1 vs Fora 1", texto)
        self.assertIn("Over 2.5 Golos", texto)
        self.assertIn("67,5%", texto)
        self.assertIn("71,9%", texto)
        self.assertIn("casa 1,90 | fora 1,20 | total 3,10", texto)
        self.assertIn("PPG recente", texto)
        self.assertIn("casa local 5", texto)
        self.assertIn("Ambas Marcam: 59,0%", texto)
        self.assertIn("Odd mínima congelada", texto)
        self.assertIn("histórica, não cotação atual", texto)
        self.assertIn("Confrontos diretos, ausências, escalações e descanso não são inferidos", texto)
        self.assertIn("excesso de confiança", texto)
        self.assertEqual(ps, antes)

    def test_ausencia_de_telemetria_nao_inventa_estatisticas(self):
        texto = gerar_estudo_jogo([snapshot(diag=False)], "1", agora=self.agora)
        self.assertIn("não guardados neste snapshot", texto)
        self.assertIn("PPG recente: indisponível", texto)
        self.assertIn("amostras", texto.lower())
        self.assertNotIn("casa 1,90", texto)
        self.assertIn("telemetria estatística suficiente", texto)

    def test_ausencia_de_odds_nao_produz_valor(self):
        p = snapshot()
        del p["odd_real"]
        texto = gerar_estudo_jogo([p], "1", agora=self.agora)
        self.assertIn("Odd real: ainda não registada", texto)
        self.assertNotIn("Primeira odd registada:", texto)
        self.assertNotIn("VALOR AGORA", texto)

    def test_contradicoes_ppg_amostra_golos(self):
        p = snapshot(mercado="Vitória Casa")
        p["diagnostico_modelo"].update({
            "lambda_casa": 0.8, "lambda_fora": 2.0, "ppg_casa": 0.7,
            "ppg_fora": 2.2, "amostra_casa_local": 2, "amostra_liga": 12,
        })
        texto = gerar_estudo_jogo([p], "1", agora=self.agora)
        self.assertIn("não favorecem a equipa da casa", texto)
        self.assertIn("PPG recente favorece a equipa visitante", texto)
        self.assertIn("inferior a 3 jogos", texto)
        self.assertIn("menos de 20 jogos", texto)

    def test_guardas_formatos_e_ranking_repetido(self):
        ps = [snapshot(), snapshot(ranking=1, mercado="Ambas Marcam")]
        self.assertIn("Formato:", gerar_estudo_jogo(ps, "texto", agora=self.agora))
        self.assertIn("Não existe previsão", gerar_estudo_jogo(ps, "19", agora=self.agora))
        self.assertIn("Ranking repetido", gerar_estudo_jogo(ps, "1", agora=self.agora))
        self.assertIn("não existem previsões", gerar_estudo_jogo([], "1", agora=self.agora))

    def test_odds_nao_sao_retratadas_como_atualizadas(self):
        p = snapshot()
        p["odd_mercado_atual"] = 1.20
        p["valor_estado"] = "expirado"
        texto = gerar_estudo_jogo([p], "1", agora=self.agora)
        self.assertIn("histórica, não cotação atual", texto)
        self.assertNotIn("1,20", texto)
        self.assertIn("Atingiu a mínima registada: sim", texto)

    def test_acesso_admin_e_resposta_no_telegram(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = 42
        bot.chat_id = 42
        bot.username = None
        hoje = datetime.now(TZ_PT) + timedelta(hours=4)
        p = snapshot(data=hoje)
        bot.previsoes = SimpleNamespace(dados={"previsoes": [p]})
        enviados = []
        bot.enviar_mensagem = lambda chat, texto: enviados.append((chat, texto))
        bot.processar_comando(42, "/estudo_jogo 1", user_id=42)
        self.assertEqual(len(enviados), 1)
        self.assertIn("ESTUDO DE JOGO — SHADOW", enviados[0][1])
        bot.processar_comando(43, "/estudo_jogo 1", user_id=43)
        self.assertEqual(len(enviados), 1)
        self.assertEqual(bot.previsoes.dados["previsoes"][0], p)


if __name__ == "__main__":
    unittest.main()
