"""Publicações owner: 20/20 previsões sem filtro comercial, por jogo e faseadas."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from publicacao_faseada_owner import (
    PublicacaoFaseadaOwner, _analise, MAX_ANALISES_DIA,
    MAX_POR_LOTE, INTERVALO_LOTES_SEG,
)
from main_competicoes import BotPremiumDiarioCompeticoes

PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2026, 11, 27, 16, 30, tzinfo=PT)


def previsao(i=1, rank=1, preco=None, minima=1.70, prob=.618):
    inicio = AGORA + timedelta(minutes=150)
    return {
        "modelo_versao": "V1.2",
        "event_id": 3000 + i,
        "data_jogo": inicio.date().isoformat(),
        "timestamp_jogo": inicio.timestamp(),
        "ranking_modelo": rank,
        "estado": "pendente",
        "casa": f"Casa {i}", "fora": f"Fora {i}", "liga": "Liga Exemplo",
        "mercado": "Over 2.5 Golos",
        "probabilidade": prob,
        "confianca_modelo": "MÉDIA",
        "qualidade": 81,
        "odd_real": preco,
        "odd_minima": minima,
    }


class PublicacaoFaseadaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "publicacoes.json"
        self.publicador = PublicacaoFaseadaOwner(self.path)

    def test_vinte_previsoes_todas_publicadas_separadamente_sem_filtro_comercial(self):
        self.assertEqual(MAX_ANALISES_DIA, 20)
        self.assertEqual(MAX_POR_LOTE, 1)
        # 3 com odds acima do mínimo, 11 abaixo e 6 sem odds. TODAS saem.
        items = [previsao(i, i,
                 preco=(1.87 if i <= 3 else 1.35 if i <= 14 else None))
                 for i in range(1, 21)]
        original = copy.deepcopy(items)
        mensagens = []
        for minuto in range(20):
            self.assertEqual(self.publicador.avisar(
                items, mensagens.append, AGORA + timedelta(minutes=minuto)
            ), 1)
        self.assertEqual(len(mensagens), 20)
        self.assertEqual(len({m.split("Casa ")[1].split(" ")[0] for m in mensagens}), 20)
        self.assertTrue(any("SEM COTAÇÃO" in m for m in mensagens))
        self.assertTrue(any("SEM VALUE" in m for m in mensagens))
        self.assertTrue(any("ACIMA DA MÍNIMA HISTÓRICA" in m for m in mensagens))
        self.assertIn("Ranking #20", mensagens[-1])
        self.assertEqual(self.publicador.avisar(items, mensagens.append, AGORA+timedelta(minutes=21)), 0)
        self.assertEqual(len(self.publicador._ler()["publicadas"]), 20)
        self.assertEqual(items, original)
        self.assertIn("20/20", self.publicador.relatorio(items, AGORA+timedelta(minutes=20)))

    def test_sem_rajadas_restart_nao_duplica(self):
        p = previsao(1, preco=1.60)
        msgs=[]
        self.assertEqual(self.publicador.avisar([p], msgs.append, AGORA), 1)
        restart = PublicacaoFaseadaOwner(self.path)
        self.assertEqual(restart.avisar([p], msgs.append, AGORA+timedelta(seconds=30)), 0)
        self.assertEqual(restart.avisar([p], msgs.append, AGORA+timedelta(minutes=1)), 0)
        self.assertEqual(len(msgs),1)

    def test_espera_intervalo_entre_mensagens(self):
        items = [previsao(1), previsao(2, 2)]
        msgs = []
        self.assertEqual(self.publicador.avisar(items, msgs.append, AGORA), 1)
        self.assertEqual(self.publicador.avisar(items, msgs.append,
                         AGORA+timedelta(seconds=INTERVALO_LOTES_SEG-1)), 0)
        self.assertEqual(self.publicador.avisar(items, msgs.append,
                         AGORA+timedelta(seconds=INTERVALO_LOTES_SEG)), 1)
        self.assertEqual(len(msgs), 2)

    def test_fora_da_janela_ou_terminado_nao_publicar(self):
        cedo = previsao(1)
        cedo["timestamp_jogo"] += 30*60
        tarde = previsao(2, 2)
        tarde["timestamp_jogo"] -= 70*60
        terminado = previsao(3, 3)
        terminado["estado"] = "ganhou"
        msgs=[]
        self.assertEqual(self.publicador.avisar([cedo, tarde, terminado],
                         msgs.append, AGORA), 0)
        self.assertEqual(len(msgs), 0)

    def test_duplicados_e_extra_vinte_e_um_nao_reabrem_coorte(self):
        items=[previsao(i, i) for i in range(1,22)]
        items.append(dict(items[0]))
        msgs=[]
        for i in range(20):
            self.publicador.avisar(items, msgs.append, AGORA+timedelta(minutes=i))
        self.assertEqual(len(msgs), 20)
        self.assertNotIn("Ranking #21", "\n".join(msgs))
        self.assertEqual(len(self.publicador._ler()["publicadas"]),20)

    def test_erro_telegram_nao_grava_marca_e_restaura(self):
        p=previsao(1,preco=1.4)
        antes=copy.deepcopy(p)
        with self.assertRaises(RuntimeError):
            self.publicador.avisar([p],lambda _:(_ for _ in ()).throw(RuntimeError("API")),AGORA)
        self.assertFalse(self.path.exists())
        msgs=[]
        self.assertEqual(PublicacaoFaseadaOwner(self.path).avisar([p],msgs.append,AGORA),1)
        self.assertIn("SEM VALUE",msgs[0])
        self.assertEqual(p,antes)

    def test_estado_corrompido_bloqueia_envio_sem_sobrescrever(self):
        self.path.write_text("{",encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.publicador.avisar([previsao(1)],lambda _:None,AGORA)
        self.assertEqual(self.path.read_text(),"{")

    def test_detalhes_diagnostico_reais_quando_disponiveis(self):
        p=previsao(1,preco=None)
        p["diagnostico_modelo"] = {
            "lambda_casa":1.68,"lambda_fora":1.11,
            "amostra_casa":10,"amostra_fora":12,
        }
        m=_analise(p)
        self.assertIn("Golos esperados pelo modelo: casa 1,68 · fora 1,11",m)
        self.assertIn("Amostra estatística: casa 10 · fora 12",m)
        self.assertIn("SEM COTAÇÃO",m)
        self.assertIn("Probabilidade do modelo: 61,8%",m)

    def test_preco_expirado_e_anomalia_sao_informados_nao_ocultados(self):
        exp=previsao(1,preco=1.90,minima=1.60)
        exp["valor_estado"]="expirado"
        self.assertIn("VALUE EXPIRADO",_analise(exp))
        inv=previsao(2,preco=2.90,minima=1.70)
        self.assertIn("PREÇO INVULGAR",_analise(inv))

    def test_comando_status_owner_e_integracao_sem_consultar_odds(self):
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=43
        bot.username=None
        bot.previsoes=SimpleNamespace(dados={"previsoes":[previsao(1)]})
        bot._publicacao_faseada_owner=self.publicador
        bot._proximo_check_publicacoes_faseadas=0
        bot.api=Mock(return_value={"message_id":1})
        bot.enviar_mensagem=Mock()
        with patch("publicacao_faseada_owner.datetime") as dt:
            dt.now.return_value=AGORA
            dt.fromtimestamp.side_effect=datetime.fromtimestamp
            bot.processar_comando(43,"/publicacoes_prejogo",user_id=43)
        self.assertIn("PUBLICAÇÕES FASEADAS",bot.enviar_mensagem.call_args.args[1])
        bot.enviar_mensagem.reset_mock()
        bot.processar_comando(44,"/publicacoes_prejogo",user_id=44)
        bot.enviar_mensagem.assert_not_called()
        with patch("publicacao_faseada_owner.datetime") as dt:
            dt.now.return_value=AGORA
            dt.fromtimestamp.side_effect=datetime.fromtimestamp
            self.assertEqual(bot._publicar_analises_faseadas_se_devido(),1)
        bot.api.assert_called_once()
        self.assertEqual(bot.api.call_args.args[0],"sendMessage")
        self.assertIn("Ranking #1",bot.api.call_args.args[1]["text"])


if __name__=="__main__":
    unittest.main()
