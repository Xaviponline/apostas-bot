"""Regressões /estudo_jogo N completo: dados verificados, sem efeitos comerciais."""
import copy
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from estudo_completo_shadow import gerar_estudo_completo, _conclusao_mercado, _nota_preco_historico
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
        self.assertIn("Tendência favorável com evidência limitada", texto)
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
        self.assertNotIn("Tendência favorável com evidência limitada", texto)
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
        self.assertIn("Tendência favorável com evidência limitada", joined)
        self.assertNotIn("90%", joined)

    def test_cinco_auditorias_amostra_conservadora(self):
        # #1 Le Mans: ambos 3/3; #2 BTTS: 3/3 e 2/3; #5 1X2 2/3 e 4/4.
        t1 = "\n".join(_conclusao_mercado("Over 2.5 Golos", {
            "casa_local": [(None, 2, 1, "R", True)] * 3,
            "fora_local": [(None, 2, 1, "R", False)] * 3,
        }))
        self.assertIn("Tendência favorável com evidência limitada", t1)
        self.assertNotIn("🟢", t1)
        t2 = "\n".join(_conclusao_mercado("Ambas Marcam", {
            "casa_local": [(None, 1, 1, "R", True)] * 3,
            "fora_local": [(None, 1, 1, "R", False)] * 2
                + [(None, 1, 0, "R", False)],
        }))
        self.assertIn("Tendência favorável com evidência limitada", t2)
        t5 = "\n".join(_conclusao_mercado("Vitória Casa", {
            "casa_local": [(None, 2, 1, "R", True)] * 2
                + [(None, 1, 2, "R", True)],
            "fora_local": [(None, 0, 2, "R", False)] * 4,
        }))
        self.assertIn("2/3", t5)
        self.assertIn("4/4", t5)
        self.assertIn("Tendência favorável com evidência limitada", t5)
        self.assertIn("proxies", t5)

    def test_tres_e_quatro_sao_parcialmente_favoraveis(self):
        # #3 Ponte Preta: 5/5 e 3/5; #4 Helmond: 3/5 e 5/5.
        dados3 = {
            "casa_local": [(None, 0, 1, "R", True)] * 5,
            "fora_local": [(None, 0, 1, "R", False)] * 3
                + [(None, 3, 1, "R", False)] * 2,
        }
        r3 = "\n".join(_conclusao_mercado("Under 2.5 Golos", dados3))
        self.assertIn("5/5", r3)
        self.assertIn("3/5", r3)
        self.assertIn("Tendência parcialmente favorável", r3)
        dados4 = {
            "casa_local": [(None, 2, 1, "R", True)] * 3
                + [(None, 0, 0, "R", True)] * 2,
            "fora_local": [(None, 2, 1, "R", False)] * 5,
        }
        r4 = "\n".join(_conclusao_mercado("Over 2.5 Golos", dados4))
        self.assertIn("3/5", r4)
        self.assertIn("5/5", r4)
        self.assertIn("Tendência parcialmente favorável", r4)

    def test_ambas_amostras_cinco_favoravel_sem_chamar_calibracao(self):
        dados = {
            "casa_local": [(None, 2, 2, "R", True)] * 4
                + [(None, 0, 0, "R", True)],
            "fora_local": [(None, 2, 2, "R", False)] * 4
                + [(None, 0, 0, "R", False)],
        }
        texto = "\n".join(_conclusao_mercado("Over 2.5 Golos", dados))
        self.assertIn("🟢 Tendência observada favorável", texto)
        self.assertIn("não valida a V1.2", texto)

    def test_preco_historico_distingue_abaixo_minimo_e_indisponivel(self):
        casos = (
            ({"odd_real": 1.35, "odd_minima": 1.52}, "abaixo do mínimo congelado"),
            ({"odd_real": 1.78, "odd_minima": 1.52}, "não demonstra VALUE"),
            ({"odd_real": None, "odd_minima": 1.51}, "Sem odd real histórica"),
            ({"odd_real": 1.62}, "mínimo congelado indisponível"),
        )
        for previsao, aviso in casos:
            copia = copy.deepcopy(previsao)
            t = "\n".join(_nota_preco_historico(previsao))
            self.assertIn(aviso, t)
            self.assertIn("não altera coorte", t)
            self.assertEqual(previsao, copia)

    def test_relatorio_completo_nao_diz_sem_consultas_e_h2h_esta_esclarecido(self):
        p = snapshot()
        texto = gerar_estudo_completo(
            p, 1, agora=AGORA, session=Sessao(historico=historico())
        )
        self.assertIn("Confrontos diretos na janela ESPN apresentados abaixo", texto)
        self.assertIn("consulta complementar ESPN separada", texto)
        self.assertNotIn("sem consultas externas", texto)
        self.assertNotIn("Janela de 70 dias limitada ao ano consultado", texto)
        self.assertIn("LEITURA DO PREÇO HISTÓRICO", texto)

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
