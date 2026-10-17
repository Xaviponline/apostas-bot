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
            snapshot(7, minutos=59, rank=6),
            snapshot(8, minutos=59, prob=float("nan")),
            snapshot(9, minutos=59, rank=2),
        ]
        dados[-1]["estado"] = "ganhou"
        mens = []
        self.assertEqual(self.alertas.avisar(dados, mens.append, agora=AGORA), 2)
        self.assertEqual(len(mens), 1)
        self.assertIn("2 seleção(ões)", mens[0])

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
        self.assertIn("2 seleção(ões)", mens[0])

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
