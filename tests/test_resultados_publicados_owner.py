"""Balanços pós-jogo exclusivamente com previsões publicadas e liquidadas."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from publicacao_faseada_owner import PublicacaoFaseadaOwner
from resultados_publicados_owner import ResultadosPublicadosOwner, _cartao_resultado
from main_competicoes import BotPremiumDiarioCompeticoes

PT = ZoneInfo("Europe/Lisbon")
MOMENTO = datetime(2026, 11, 27, 16, 30, tzinfo=PT)


def previsao(i=1, rank=1, preco=1.85):
    ini = MOMENTO + timedelta(hours=2, minutes=30)
    return {
        "modelo_versao": "V1.2", "event_id": 5100 + i,
        "data_jogo": ini.date().isoformat(),
        "timestamp_jogo": ini.timestamp(), "ranking_modelo": rank,
        "casa": f"Casa {i}", "fora": f"Fora {i}", "liga": "Liga Exemplo",
        "mercado": "Over 2.5 Golos", "probabilidade": .61,
        "confianca_modelo": "MÉDIA", "qualidade": 81,
        "odd_real": preco, "odd_minima": 1.73,
        "estado": "pendente", "resultado_binario": None,
        "golos_casa": None, "golos_fora": None, "liquidada_em": None,
    }


def liquidar(p, gc=2, gf=1):
    p["estado"] = "ganhou" if gc + gf >= 3 else "perdeu"
    p["resultado_binario"] = int(gc + gf >= 3)
    p["golos_casa"], p["golos_fora"] = gc, gf
    p["liquidada_em"] = "2026-11-27T22:30:00Z"


class ResultadosOwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pasta = Path(self.tmp.name)
        self.publicador = PublicacaoFaseadaOwner(pasta / "publicacoes.json")
        self.resultados = ResultadosPublicadosOwner(pasta / "resultados.json")
        self.liquida = MOMENTO + timedelta(hours=6)

    def test_notifica_resultado_acerto_e_falha_apos_liquidacao(self):
        ps = [previsao(1), previsao(2, 2)]
        iniciais = copy.deepcopy(ps)
        publicadas = []
        self.assertEqual(self.publicador.avisar(ps, publicadas.append, MOMENTO), 1)
        self.assertEqual(self.publicador.avisar(
            ps, publicadas.append, MOMENTO + timedelta(minutes=1)
        ), 1)
        # Sem jogos liquidados, nenhum novo aviso de resultados.
        msgs = []
        self.assertEqual(self.resultados.avisar(ps, self.publicador, msgs.append, self.liquida), 0)
        self.assertEqual(ps, iniciais)
        liquidar(ps[0], 2, 1)
        liquidar(ps[1], 0, 0)
        self.assertEqual(self.resultados.avisar(ps, self.publicador, msgs.append, self.liquida), 2)
        self.assertEqual(len(msgs), 2)
        self.assertIn("Casa 1 2–1 Fora 1", msgs[0])
        self.assertIn("✅ PREVISÃO ACERTADA", msgs[0])
        self.assertIn("❌ PREVISÃO FALHADA", msgs[1])
        self.assertIn("Probabilidade estimada antes do jogo: 61,0%", msgs[0])
        self.assertIn("Odd registada antes do jogo: 1,85", msgs[0])
        self.assertEqual(self.resultados.avisar(
            ps, self.publicador, msgs.append, self.liquida+timedelta(minutes=1)
        ), 0)
        self.assertEqual(len(self.resultados._ler()["enviados"]), 2)

    def test_sem_publicacao_previa_nao_emite(self):
        p = previsao()
        liquidar(p)
        out = []
        self.assertEqual(self.resultados.avisar([p], self.publicador, out.append, self.liquida), 0)
        self.assertFalse(out)
        self.assertFalse(self.resultados.path.exists())

    def test_estado_nao_final_ou_placar_incoerente_nao_notifica(self):
        p = previsao()
        self.publicador.avisar([p], lambda _: None, MOMENTO)
        p["estado"] = "ganhou"
        p["resultado_binario"] = 1
        p["golos_casa"], p["golos_fora"] = 0, 0
        p["liquidada_em"] = "2026-11-27T22:30:00Z"
        self.assertEqual(self.resultados.avisar([p], self.publicador, Mock(), self.liquida), 0)
        p["golos_casa"], p["golos_fora"] = 2, 1
        p["liquidada_em"] = None
        self.assertEqual(self.resultados.avisar([p], self.publicador, Mock(), self.liquida), 0)
        p["liquidada_em"] = "2026-11-27T22:30:00Z"
        p["resultado_binario"] = True  # bool não é marcador binário válido
        self.assertEqual(self.resultados.avisar([p], self.publicador, Mock(), self.liquida), 0)

    def test_erro_telegram_so_repete_parte_nao_confirmada(self):
        ps = [previsao(1), previsao(2, 2)]
        self.publicador.avisar(ps, Mock(), MOMENTO)
        self.publicador.avisar(ps, Mock(), MOMENTO+timedelta(minutes=1))
        for p in ps:
            liquidar(p)
        msgs=[]
        def enviar(msg):
            msgs.append(msg)
            if "Casa 2" in msg and msgs.count(msg)==1:
                raise RuntimeError("Telegram sem resposta")
        with self.assertRaises(RuntimeError):
            self.resultados.avisar(ps, self.publicador, enviar, self.liquida)
        self.assertEqual(len(self.resultados._ler()["enviados"]), 1)
        self.assertEqual(ResultadosPublicadosOwner(self.resultados.path).avisar(
            ps, self.publicador, enviar, self.liquida+timedelta(minutes=1)
        ), 1)
        self.assertEqual(len(self.resultados._ler()["enviados"]), 2)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[1], msgs[2])

    def test_corrompido_bloqueia_notificacao_sem_sobrescrever(self):
        p=previsao()
        self.publicador.avisar([p], Mock(), MOMENTO)
        liquidar(p)
        self.resultados.path.write_text("{",encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.resultados.avisar([p],self.publicador,Mock(),self.liquida)
        self.assertEqual(self.resultados.path.read_text(),"{")

    def test_placar_ausente_rede_e_odd_ausente_nao_inventados(self):
        p = previsao(preco=None)
        liquidar(p, 0, 0)
        txt = _cartao_resultado(p)
        self.assertIn("Casa 1 0–0 Fora 1", txt)
        self.assertIn("❌ PREVISÃO FALHADA", txt)
        self.assertIn("Sem odd pré-jogo registada", txt)
        self.assertNotIn("ROI", txt)
        self.assertNotIn("Lucro", txt)

    def test_previsoes_antigas_ou_fora_top20_nao_notificadas(self):
        p = previsao()
        self.publicador.avisar([p], Mock(), MOMENTO)
        liquidar(p)
        p["timestamp_jogo"] -= 9*86400
        p["data_jogo"] = "2026-11-18"
        # Chave do snapshot mudou, e tempo fora da janela de retenção.
        self.assertEqual(self.resultados.avisar([p], self.publicador, Mock(), self.liquida), 0)

    def test_status_owner_apenas_leitura_e_sem_espn(self):
        p = previsao()
        self.publicador.avisar([p], Mock(), MOMENTO)
        liquidar(p)
        read_before = copy.deepcopy(p)
        txt = self.resultados.relatorio([p], self.publicador, self.liquida)
        self.assertIn("RESULTADOS DAS ANÁLISES",txt)
        self.assertIn("liquidados ainda por notificar",txt)
        self.assertEqual(p,read_before)
        self.assertFalse(self.resultados.path.exists())

    def test_comando_owner_e_fluxo_producao_sem_novas_apis(self):
        p = previsao()
        self.publicador.avisar([p], Mock(), MOMENTO)
        liquidar(p)
        b = BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id = b.chat_id = 43
        b.username = None
        b.previsoes = SimpleNamespace(dados={"previsoes": [p]})
        b._publicacao_faseada_owner = self.publicador
        b._resultados_publicados_owner = self.resultados
        b._proximo_check_resultados_owner = 0
        b.api = Mock(return_value={"message_id": 1})
        b.enviar_mensagem = Mock()
        with patch("resultados_publicados_owner.datetime") as dt:
            dt.now.return_value = self.liquida
            dt.fromtimestamp.side_effect = datetime.fromtimestamp
            b.processar_comando(43, "/resultados_previsoes", user_id=43)
            self.assertIn("RESULTADOS DAS ANÁLISES", b.enviar_mensagem.call_args.args[1])
            b.enviar_mensagem.reset_mock()
            b.processar_comando(44, "/resultados_previsoes", user_id=44)
            b.enviar_mensagem.assert_not_called()
            self.assertEqual(b._avisar_resultados_owner_se_devido(), 1)
        self.assertEqual(b.api.call_count, 1)
        self.assertIn("PREVISÃO ACERTADA", b.api.call_args.args[1]["text"])
        self.assertEqual(self.resultados.avisar(
            [p], self.publicador, Mock(), self.liquida + timedelta(minutes=2)
        ), 0)

    def test_liquidacao_existente_desencadeia_aviso_mas_nao_mais_espn(self):
        p=previsao()
        self.publicador.avisar([p], Mock(), MOMENTO)
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=43
        bot.previsoes=SimpleNamespace(dados={"previsoes":[p]})
        bot._publicacao_faseada_owner=self.publicador
        bot._resultados_publicados_owner=self.resultados
        bot._proximo_check_resultados_owner=0
        bot.api=Mock(return_value={"message_id":1})
        bot._rotinas_diarias=Mock()
        bot._rotinas_diarias.liquidar_se_devido.side_effect=lambda _: liquidar(p) or 1
        bot._rotinas_diarias.enviar_relatorio_se_devido.return_value=False
        bot._publicar_analises_faseadas_se_devido=Mock()
        bot._avisar_prejogo_se_devido=Mock()
        bot._scout_auto_se_devido=Mock()
        bot._fonte_alt_auto_se_devido=Mock()
        with patch("resultados_publicados_owner.datetime") as dt:
            dt.now.return_value=self.liquida
            dt.fromtimestamp.side_effect=datetime.fromtimestamp
            bot._rotinas_diarias_se_devido()
        bot._rotinas_diarias.liquidar_se_devido.assert_called_once()
        bot.api.assert_called_once()
        self.assertIn("Casa 1 2–1 Fora 1", bot.api.call_args.args[1]["text"])


if __name__=="__main__":
    unittest.main()
