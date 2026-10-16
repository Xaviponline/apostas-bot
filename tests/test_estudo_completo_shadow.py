"""Regressões /estudo_jogo N completo: dados verificados, sem efeitos comerciais."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from estudo_completo_shadow import gerar_estudo_completo, _conclusao_mercado
from main_competicoes import BotPremiumDiarioCompeticoes
from test_estudo_forma_espn import Sessao, event, snapshot


TZ_PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 16, 11, tzinfo=TZ_PT)


def historico(marcados=True):
    """Três jogos locais para cada equipa em dias pré-snapshot."""
    if marcados:
        c = [(2, 1), (3, 1), (2, 2)]
        f = [(1, 2), (2, 2), (1, 3)]  # score casa-fora, Toulouse visitante
    else:
        c = [(0, 0), (0, 1), (1, 0)]
        f = [(1, 0), (0, 0), (1, 1)]
    jogos = []
    for k, (gc, gf) in enumerate(c):
        jogos.append(event(
            100+k, f"2030-10-{12-k:02d}", home_id=101, away_id=300+k,
            gols_home=gc, gols_away=gf, home_name="Casa Real", away_name=f"Rival H{k}",
        ))
    for k, (gc, gf) in enumerate(f):
        jogos.append(event(
            200+k, f"2030-10-{9-k:02d}", home_id=400+k, away_id=202,
            gols_home=gc, gols_away=gf, home_name=f"Rival F{k}", away_name="Visitante Real",
        ))
    return jogos


class EstudoCompletoTests(unittest.TestCase):
    def test_report_favoravel_usa_uma_consulta_espn_e_protege_snapshot(self):
        p = snapshot()
        p.update({
            "probabilidade": 0.69, "probabilidade_bruta": 0.74,
            "odd_minima": 1.50, "odd_real": 1.62, "qualidade": 75,
        })
        p["diagnostico_modelo"].update({
            "lambda_casa": 2.02, "lambda_fora": 1.90,
            "ppg_casa": 1.0, "ppg_fora": 1.0,
            "amostra_casa_local": 3, "amostra_fora_local": 3,
            "media_liga_casa": 1.67, "media_liga_fora": 1.24,
        })
        antes = copy.deepcopy(p)
        session = Sessao(historico=historico(marcados=True))
        texto = gerar_estudo_completo(p, 1, agora=AGORA, session=session)
        self.assertIn("ESTUDO COMPLETO — SHADOW", texto)
        self.assertIn("Probabilidade V1.2: 69,0%", texto)
        self.assertIn("CRUZAMENTO — V1.2", texto)
        self.assertIn("Over 2.5 Golos, equipa da casa em casa: 3/3", texto)
        self.assertIn("Over 2.5 Golos, visitantes fora: 3/3", texto)
        self.assertIn("Tendência observada concordante", texto)
        self.assertIn("amostra casa/fora curta", texto.lower())
        self.assertIn("não são validação estatística independente", texto)
        self.assertIn("FORMA RECENTE — ESPN", texto)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(p, antes)

    def test_mercado_contrariado_e_alerta_sem_reclassificacao(self):
        p = snapshot()
        sessao = Sessao(historico=historico(marcados=False))
        texto = gerar_estudo_completo(p, 1, agora=AGORA, session=sessao)
        self.assertIn("Possível contradição", texto)
        self.assertIn("0/3 jogos", texto)
        self.assertIn("probabilidade v1.2", texto.lower())
        self.assertEqual(len(sessao.calls), 2)

    def test_falha_espn_sem_cruzamento_e_sem_dados_inventados(self):
        p = snapshot()
        sessao = Sessao(status=503)
        antes = copy.deepcopy(p)
        texto = gerar_estudo_completo(p, 1, agora=AGORA, session=sessao)
        self.assertIn("Cruzamento automático suspenso", texto)
        self.assertIn("calendário do jogo: HTTP 503", texto)
        self.assertNotIn("Tendência observada concordante", texto)
        self.assertEqual(len(sessao.calls), 1)
        self.assertEqual(p, antes)

    def test_mercado_1x2_usa_proxies_e_nao_chama_probabilidade(self):
        dados = {
            "casa_local": [(None, 2, 1, "R", True)] * 3,
            "fora_local": [(None, 0, 1, "R", False)] * 3,
        }
        linhas = _conclusao_mercado("Vitória Casa", dados)
        joined = "\n".join(linhas)
        self.assertIn("3/3", joined)
        self.assertIn("proxies", joined)
        self.assertIn("Tendência observada concordante", joined)
        self.assertNotIn("90%", joined)

    def test_amostras_menores_que_tres_nao_concluem(self):
        dados = {
            "casa_local": [(None, 2, 1, "R", True)],
            "fora_local": [(None, 2, 1, "R", False)] * 3,
        }
        texto = "\n".join(_conclusao_mercado("Ambas Marcam", dados))
        self.assertIn("Amostra local insuficiente", texto)
        self.assertNotIn("concordante", texto)

    def test_data_ou_versao_divergente_nao_consulta_espn(self):
        p = snapshot()
        s = Sessao()
        self.assertIn("indisponível", gerar_estudo_completo(p, 2, agora=AGORA, session=s))
        p["modelo_versao"] = "Platt_SHADOW"
        self.assertIn("indisponível", gerar_estudo_completo(p, 1, agora=AGORA, session=s))
        self.assertEqual(s.calls, [])

    def test_telegram_apenas_owner_e_nao_dispara_modo_completo_no_estudo_normal(self):
        bot = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id = bot.chat_id = 42
        bot.username = None
        hoje = datetime.now(TZ_PT)
        p = snapshot()
        p["data_jogo"] = hoje.strftime("%Y-%m-%d")
        p["timestamp_jogo"] = (hoje + timedelta(hours=3)).timestamp()
        p["criada_em"] = (hoje - timedelta(hours=1)).isoformat()
        bot.previsoes = SimpleNamespace(dados={"previsoes": [p]})
        inicial = copy.deepcopy(bot.previsoes.dados)
        enviados = []
        bot.enviar_mensagem = lambda chat, msg: enviados.append((chat, msg))
        with patch("estudo_completo_shadow.gerar_estudo_completo", return_value="RELATORIO_TESTE") as analisar:
            bot.processar_comando(42, "/estudo_jogo 1 completo", user_id=42)
            self.assertEqual(enviados, [(42, "RELATORIO_TESTE")])
            self.assertEqual(analisar.call_count, 1)
            bot.processar_comando(43, "/estudo_jogo 1 completo", user_id=43)
            self.assertEqual(len(enviados), 1)
            self.assertEqual(analisar.call_count, 1)
            bot.processar_comando(42, "/estudo_jogo", user_id=42)
            self.assertIn("completo", enviados[-1][1])
            self.assertEqual(analisar.call_count, 1)
        self.assertEqual(bot.previsoes.dados, inicial)


if __name__ == "__main__":
    unittest.main()
