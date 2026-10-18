"""Validação das notificações OWNER T-60m, sem APIs pagas."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from alertas_prejogo import AlertasPreJogo
from odds_rastreio import RastreioOdds
from main_competicoes import BotPremiumDiarioCompeticoes


TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 10, 17, 16, 0, tzinfo=TZ)


def snapshot(i=1, minutos=60, rank=3, prob=0.696, odd=2.02, minima=1.51,
             evento=None, mercado="Under 2.5 Golos"):
    inicio = AGORA + timedelta(minutes=minutos)
    return {
        "event_id": i if evento is None else evento,
        "data_jogo": inicio.date().isoformat(),
        "timestamp_jogo": inicio.timestamp(),
        "casa": "Peterborough United", "fora": "Burton Albion",
        "liga": "🇬🇧 League One", "mercado": mercado,
        "modelo_versao": "V1.2", "ranking_modelo": rank,
        "probabilidade": prob, "confianca_modelo": "ALTA",
        "odd_real": odd, "odd_minima": minima,
        "odd_justa": 1.44, "qualidade": 100,
        "estado": "pendente",
        "valor_estado": "confirmado" if odd is not None and odd >= minima else "sem_valor",
    }


class AlertaPreJogoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "alertas_owner.json"
        self.alertas = AlertasPreJogo(self.path)

    def test_17h_alerta_as_16h_uma_vez_com_mensagem_completa(self):
        dados = [snapshot()]
        original = copy.deepcopy(dados)
        mensagens = []
        self.assertEqual(self.alertas.avisar(dados, mensagens.append, agora=AGORA), 1)
        self.assertEqual(len(mensagens), 1)
        for esperado in ("17:00", "RANKING #3", "Peterborough United",
                         "Under 2.5 Golos", "69,6%", "2,02", "Mín. 1,51",
                         "Odd justa 1,44", "100/100", "RISCO MUITO ELEVADO",
                         "EV do modelo"):
            self.assertIn(esperado, mensagens[0])
        self.assertEqual(dados, original)
        self.assertEqual(
            AlertasPreJogo(self.path).avisar(
                dados, mensagens.append, agora=AGORA + timedelta(minutes=5)
            ), 0
        )
        self.assertEqual(len(mensagens), 1)

    def test_janelas_elegibilidade_e_exclusao_iniciados_e_fora_rank(self):
        dados = [
            snapshot(1, minutos=75),
            snapshot(2, minutos=61),
            snapshot(3, minutos=60),
            snapshot(4, minutos=46),
            snapshot(5, minutos=44),
            snapshot(6, minutos=-10),
            snapshot(7, minutos=59, rank=21),
            snapshot(8, minutos=59, prob=float("nan")),
            snapshot(9, minutos=59, rank=2),
        ]
        dados[-1]["estado"] = "ganhou"
        mens = []
        self.assertEqual(self.alertas.avisar(dados, mens.append, agora=AGORA), 2)
        self.assertEqual(len(mens), 1)
        self.assertIn("2 seleções", mens[0])

    def test_sem_odd_abaixo_ou_expirada_todos_devidamente_assinalados(self):
        d1 = snapshot(10, odd=None)
        d2 = snapshot(11, odd=1.30)
        d3 = snapshot(12, odd=1.70)
        d3["valor_estado"] = "expirado"
        d3["odd_mercado_atual"] = 1.20
        mens = []
        self.assertEqual(self.alertas.avisar([d1, d2, d3], mens.append, agora=AGORA), 3)
        texto = mens[0]
        self.assertIn("sem odd registada", texto)
        self.assertIn("inferior à mínima", texto)
        self.assertIn("VALUE histórico expirado", texto)
        self.assertIn("não são em direto", texto) if "não são em direto" in texto else None

    def test_falha_envio_nao_marca_e_permite_nova_tentativa(self):
        dados = [snapshot()]
        def falhar(msg):
            raise RuntimeError("falhou telegram")
        with self.assertRaises(RuntimeError):
            self.alertas.avisar(dados, falhar, agora=AGORA)
        self.assertFalse(self.path.exists())
        mens = []
        self.assertEqual(self.alertas.avisar(dados, mens.append, agora=AGORA), 1)
        self.assertEqual(len(mens), 1)

    def test_marcador_corrompido_falha_fechado_sem_reescrever(self):
        self.path.write_text('{"dados":"outro"}', encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.alertas.avisar([snapshot()], lambda msg: None, agora=AGORA)
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"dados":"outro"}')

    def test_dois_mercados_mesmo_evento_sao_distintos_e_ranking_nao_duplica(self):
        d1 = snapshot(9, rank=2, mercado="Under 2.5 Golos")
        d2 = snapshot(9, rank=4, mercado="Over 2.5 Golos")
        d3 = snapshot(9, rank=3, mercado="Under 2.5 Golos")
        mens = []
        self.assertEqual(self.alertas.avisar([d1, d2, d3], mens.append, agora=AGORA), 2)
        self.assertEqual(len(mens), 1)
        self.assertIn("2 seleções", mens[0])

    def test_todos_os_rankings_de_um_a_vinte_e_nao_so_top5(self):
        rankings = [1, 5, 6, 13, 14, 17, 19, 20]
        dados = [snapshot(200 + rank, rank=rank) for rank in rankings]
        mensagens = []
        self.assertEqual(self.alertas.avisar(dados, mensagens.append, agora=AGORA), 8)
        self.assertEqual(len(mensagens), 2)  # 4 cartões por mensagem
        corpo = "\n".join(mensagens)
        for rank in rankings:
            self.assertIn(f"RANKING #{rank}", corpo)
        self.assertIn("máx. 20", corpo)
        self.assertNotIn("Top 5 congeladas", corpo)
        relatorio = self.alertas.relatorio(dados, agora=AGORA)
        self.assertIn("Ranking #1–#20", relatorio)
        self.assertIn("8/20", relatorio)

    def test_no_maximo_20_do_dia_e_analise_repetida_nao_acrescenta(self):
        # Primeira análise com 20 seleções. Uma segunda ronda pode ter ranks
        # iguais e +10 jogos; não devem originar 30 alertas diários.
        originais = [snapshot(i, rank=i) for i in range(1, 21)]
        adicionais = [snapshot(i, rank=(i % 20) + 1) for i in range(21, 31)]
        dados = originais + adicionais
        antes = copy.deepcopy(dados)
        mensagens = []
        self.assertEqual(self.alertas.avisar(dados, mensagens.append, agora=AGORA), 20)
        self.assertEqual(len(mensagens), 5)
        self.assertEqual(dados, antes)
        self.assertEqual(self.alertas.avisar(dados, mensagens.append,
                                            agora=AGORA + timedelta(minutes=5)), 0)
        self.assertEqual(len(mensagens), 5)
        self.assertIn("20/20", self.alertas.relatorio(dados, agora=AGORA))
        # Uma seleção concluída continua a contar para a coorte de 20;
        # não substituir por picks novas após o início.
        dados[0]["estado"] = "ganhou"
        self.assertEqual(len(self.alertas._selecoes_do_dia(dados, AGORA)), 20)
        self.assertEqual(self.alertas.avisar(dados, mensagens.append, agora=AGORA), 0)

    def test_seis_picks_hoje_incluem_rankings_13_14_17_e_19(self):
        dados = [
            snapshot(101, rank=14, minutos=60),
            snapshot(102, rank=13, minutos=60),
            snapshot(103, rank=5, minutos=60),
            snapshot(104, rank=17, minutos=60),
            snapshot(105, rank=19, minutos=60, odd=1.39),
            snapshot(106, rank=19, minutos=60, odd=None),
        ]
        self.assertIn("6/20", self.alertas.relatorio(dados, agora=AGORA))
        mensagens = []
        self.assertEqual(self.alertas.avisar(dados, mensagens.append, agora=AGORA), 6)
        tudo = "\n".join(mensagens)
        for ranking in (5, 13, 14, 17, 19):
            self.assertIn(f"RANKING #{ranking}", tudo)
        self.assertIn("sem odd registada", tudo)
        self.assertIn("inferior à mínima", tudo)

    def test_ranking_vinte_um_nao_enviado(self):
        dados = [snapshot(100, rank=20), snapshot(101, rank=21)]
        mensagens = []
        self.assertEqual(self.alertas.avisar(dados, mensagens.append, agora=AGORA), 1)
        self.assertIn("RANKING #20", mensagens[0])
        self.assertNotIn("RANKING #21", mensagens[0])

    def test_estado_read_only_e_guardado_na_reinicializacao(self):
        self.alertas.avisar([snapshot()], lambda msg: None, agora=AGORA)
        antes = self.path.read_bytes()
        texto = AlertasPreJogo(self.path).relatorio([snapshot()], agora=AGORA)
        self.assertIn("Alertas já enviados hoje: 1", texto)
        self.assertIn("não avisadas: 0", texto)
        self.assertEqual(self.path.read_bytes(), antes)

    def test_envia_lotes_sem_marcar_o_falhado(self):
        dados = [snapshot(i, rank=(i % 5) + 1) for i in range(1, 6)]
        mensagens = []
        def func(texto):
            if mensagens:
                raise RuntimeError("segundo lote falhou")
            mensagens.append(texto)
        with self.assertRaises(RuntimeError):
            self.alertas.avisar(dados, func, agora=AGORA)
        estado = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(estado["avisados"]), 4)
        r = self.alertas.avisar(dados, mensagens.append, agora=AGORA)
        self.assertEqual(r, 1)
        self.assertEqual(len(mensagens), 2)

    def test_celtic_sem_odd_historica_mostra_consulta_em_vez_de_reconfirmacao(self):
        dados = [snapshot(25, rank=13, odd=None, prob=0.684, minima=1.53)]
        dados[0]["casa"] = "Celtic"
        dados[0]["fora"] = "Heart of Midlothian"
        dados[0]["qualidade"] = 81
        rastreio_path = Path(self.tmp.name) / "rastreio_celtic.jsonl"
        rastreio_path.write_text(json.dumps({
            "event_id_modelo": "25",
            "mercado_modelo": "Under 2.5 Golos",
            "timestamp_jogo": dados[0]["timestamp_jogo"],
            "observado_em": (AGORA - timedelta(minutes=28)).isoformat(),
            "odd_observada": None,
            "diagnostico": "betano_sem_odds_no_evento",
        }) + "\\n", encoding="utf-8")
        alertas = AlertasPreJogo(self.path, rastreio=RastreioOdds(rastreio_path))
        originais = copy.deepcopy(dados)
        enviados = []
        self.assertEqual(alertas.avisar(dados, enviados.append, agora=AGORA), 1)
        texto = enviados[0]
        self.assertIn("1 seleção da análise diária", texto)
        self.assertNotIn("seleção(ões)", texto)
        self.assertIn("RISCO DE PREÇO — sem odd registada", texto)
        self.assertIn("Última consulta às 15:32: betano_sem_odds_no_evento", texto)
        self.assertIn("sem cotação válida; VALUE não confirmado", texto)
        self.assertNotIn("PREÇO NÃO RECONFIRMADO", texto)
        self.assertIn("odds históricas ou ausentes", texto)
        self.assertEqual(dados, originais)

    def test_sem_odd_sem_rastreio_nao_inventa_reconfirmacao(self):
        dados = [snapshot(26, odd=None)]
        enviados = []
        self.assertEqual(self.alertas.avisar(dados, enviados.append, agora=AGORA), 1)
        self.assertIn("SEM COTAÇÃO OBSERVADA", enviados[0])
        self.assertNotIn("PREÇO NÃO RECONFIRMADO", enviados[0])

    def test_alerta_mostra_preco_nao_reconfirmado_apos_falha_mercado(self):
        dados = [snapshot(21)]
        original = copy.deepcopy(dados)
        rastreio_path = Path(self.tmp.name) / "rastreio.jsonl"
        observacoes = [
            (AGORA - timedelta(minutes=120), 2.02, ""),
            (AGORA - timedelta(minutes=12), None, "mercado_nao_disponivel"),
        ]
        with rastreio_path.open("w", encoding="utf-8") as f:
            for quando, odd, diag in observacoes:
                f.write(json.dumps({
                    "event_id_modelo": "21", "mercado_modelo": "Under 2.5 Golos",
                    "timestamp_jogo": dados[0]["timestamp_jogo"],
                    "observado_em": quando.isoformat(),
                    "odd_observada": odd, "diagnostico": diag,
                }) + "\n")
        conteudo = rastreio_path.read_bytes()
        alerta = AlertasPreJogo(self.path, rastreio=RastreioOdds(rastreio_path))
        mensagens = []
        self.assertEqual(alerta.avisar(dados, mensagens.append, agora=AGORA), 1)
        self.assertIn("PREÇO NÃO RECONFIRMADO às 15:48", mensagens[0])
        self.assertIn("mercado_nao_disponivel", mensagens[0])
        self.assertIn("Odd registada 2,02", mensagens[0])
        self.assertEqual(dados, original)
        self.assertEqual(rastreio_path.read_bytes(), conteudo)
        self.assertEqual(alerta.avisar(dados, mensagens.append, agora=AGORA + timedelta(minutes=2)), 0)
        self.assertEqual(len(mensagens), 1)

    def test_alerta_ultima_odd_nao_e_apresentada_como_preco_atual(self):
        dados = [snapshot(22)]
        rastreio_path = Path(self.tmp.name) / "rastreio.jsonl"
        rastreio_path.write_text(json.dumps({
            "event_id_modelo": "22", "mercado_modelo": "Under 2.5 Golos",
            "timestamp_jogo": dados[0]["timestamp_jogo"],
            "observado_em": (AGORA - timedelta(minutes=17)).isoformat(),
            "odd_observada": 1.65,
        }) + "\n", encoding="utf-8")
        mensagens = []
        AlertasPreJogo(self.path, rastreio=RastreioOdds(rastreio_path)).avisar(
            dados, mensagens.append, agora=AGORA
        )
        self.assertIn("Última observação 15:43: odd 1,65", mensagens[0])
        self.assertIn("não confirma disponibilidade agora", mensagens[0])

    def test_outro_evento_mercado_e_obs_futura_nao_contaminam_alerta(self):
        dados = [snapshot(23)]
        rastreio_path = Path(self.tmp.name) / "rastreio.jsonl"
        linhas = [
            {"event_id_modelo": "23", "mercado_modelo": "Ambas Marcam",
             "timestamp_jogo": dados[0]["timestamp_jogo"],
             "observado_em": (AGORA - timedelta(minutes=5)).isoformat(),
             "diagnostico": "mercado_nao_disponivel"},
            {"event_id_modelo": "999", "mercado_modelo": "Under 2.5 Golos",
             "timestamp_jogo": dados[0]["timestamp_jogo"],
             "observado_em": (AGORA - timedelta(minutes=5)).isoformat(),
             "diagnostico": "mercado_nao_disponivel"},
            {"event_id_modelo": "23", "mercado_modelo": "Under 2.5 Golos",
             "timestamp_jogo": dados[0]["timestamp_jogo"],
             "observado_em": (AGORA + timedelta(minutes=5)).isoformat(),
             "diagnostico": "mercado_nao_disponivel"},
        ]
        rastreio_path.write_text("".join(json.dumps(x) + "\n" for x in linhas), encoding="utf-8")
        mensagens = []
        AlertasPreJogo(self.path, rastreio=RastreioOdds(rastreio_path)).avisar(
            dados, mensagens.append, agora=AGORA
        )
        self.assertIn("PREÇO HISTÓRICO — sem observação local posterior", mensagens[0])
        self.assertNotIn("mercado_nao_disponivel", mensagens[0])

    def test_rastreio_ilegivel_nao_bloqueia_alerta_e_mantem_integridade(self):
        dados = [snapshot(24)]
        rastreio_path = Path(self.tmp.name) / "rastreio.jsonl"
        rastreio_path.write_text("JSON inválido", encoding="utf-8")
        original = rastreio_path.read_bytes()
        mensagens = []
        alerta = AlertasPreJogo(self.path, rastreio=RastreioOdds(rastreio_path))
        self.assertEqual(alerta.avisar(dados, mensagens.append, agora=AGORA), 1)
        self.assertIn("PREÇO HISTÓRICO — sem observação local posterior", mensagens[0])
        self.assertEqual(rastreio_path.read_bytes(), original)

    def test_comando_owner_sem_envio_e_tarefa_automatica(self):
        b = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id = b.chat_id = 43
        b.username = None
        b.previsoes = SimpleNamespace(dados={"previsoes": [snapshot()]})
        b._alertas_prejogo = self.alertas
        b._proximo_check_prejogo = 0
        mensagens = []
        b.enviar_mensagem = lambda chat, msg: mensagens.append((chat, msg))
        with patch("alertas_prejogo.datetime") as mocked:
            # o comando e o envio usam a hora real por omissão; mock targeted.
            mocked.now.return_value = AGORA
            mocked.fromtimestamp.side_effect = datetime.fromtimestamp
            b.processar_comando(43, "/alertas_prejogo", user_id=43)
            self.assertEqual(len(mensagens), 1)
            self.assertIn("ALERTAS PRÉ-JOGO", mensagens[0][1])
            b.processar_comando(44, "/alertas_prejogo", user_id=44)
            self.assertEqual(len(mensagens), 1)
            self.assertEqual(b._avisar_prejogo_se_devido(), 1)
            self.assertEqual(b._avisar_prejogo_se_devido(), 0)
        self.assertEqual(len(mensagens), 2)
        self.assertIn("RANKING #3", mensagens[1][1])
        self.assertEqual(mensagens[1][0], 43)


if __name__ == "__main__":
    unittest.main()
