"""Testa corte fixo, identidade ESPN, captura pré-jogo e comando OWNER só leitura."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lambda_validacao_shadow import relatorio_lambda_validacao
from main_competicoes import BotPremiumDiarioCompeticoes

MERCADOS=("Vitória Casa","Empate","Vitória Fora")


def snapshot(jid, day=29, hora=19, capture_min=-120, liga="eng.2"):
    kickoff=datetime(2026,11,day,hora,tzinfo=timezone.utc)
    ts=kickoff.timestamp()
    jogo={"id":jid,"casa_id":jid+101,"fora_id":jid+201,"timestamp":ts}
    return {
        "versao":1, "capturado_em_utc":(kickoff+timedelta(minutes=capture_min)).isoformat(),
        "liga_codigo":liga,"chave":f"{liga}|{jid}|{ts}",
        "jogo":jogo,
        "original_1x2":dict(zip(MERCADOS,(.5,.3,.2))),
        "alternativa_1x2":dict(zip(MERCADOS,(.6,.2,.2))),
    }


def final(reg, score=(2,0)):
    return {"chave":reg["chave"],"liga_codigo":reg["liga_codigo"],"jogo":reg["jogo"],
            "golos_casa":score[0],"golos_fora":score[1],"fonte":"ESPN_STATUS_FINAL"}


def write(path,rows):
    path.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")


class LambdaValidacaoTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.path=Path(td.name)/"lambda_prospectivo_shadow.jsonl"
        self.res=self.path.with_name("lambda_prospectivo_resultados.jsonl")

    def test_sem_ficheiro(self):
        self.assertIn("sem snapshots",relatorio_lambda_validacao(self.path).lower())

    def test_legacy_fora_e_futuros_contados_antes_de_resultado(self):
        velho=snapshot(1,day=27)
        novo=snapshot(2,day=29)
        proximo=snapshot(3,day=30)
        write(self.path,[velho,novo,proximo])
        write(self.res,[final(velho),final(novo)])
        raw=self.path.read_bytes(),self.res.read_bytes()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP proibido")):
            msg=relatorio_lambda_validacao(self.path)
        self.assertEqual(raw,(self.path.read_bytes(),self.res.read_bytes()))
        self.assertIn("Novos snapshots pré-jogo: 2 | finais ESPN exatos: 1 | sem final: 1",msg)
        self.assertIn("Dias com snapshots: 2 | dias com resultados: 1",msg)
        self.assertIn("1/200 resultados e 1/20 dias",msg)
        self.assertIn("RECOLHA",msg)
        self.assertNotIn("IC exploratório",msg)

    def test_corte_captura_repetidos_conflitos_e_estado_espn(self):
        pre=snapshot(11,day=28,hora=0,capture_min=-2)  # captura antes do corte
        pos=snapshot(12,day=28,hora=19,capture_min=10)  # captura pós-jogo
        certo=snapshot(13,day=28,hora=19,capture_min=-30)
        confl=snapshot(14,day=29,hora=19,capture_min=-60)
        unverified=snapshot(15,day=30,hora=19,capture_min=-60)
        errado=final(unverified); errado["jogo"]={**errado["jogo"],"timestamp":errado["jogo"]["timestamp"]+10}
        write(self.path,[pre,pos,certo,confl,unverified,certo])
        write(self.res,[final(pre),final(pos),final(certo),final(confl),final(confl,score=(1,1)),errado])
        msg=relatorio_lambda_validacao(self.path)
        self.assertIn("Novos snapshots pré-jogo: 3 | finais ESPN exatos: 1 | sem final: 1",msg)
        self.assertIn("Finais ESPN contraditórios excluídos: 1",msg)
        self.assertIn("Capturas tardias excluídas: 1",msg)
        self.assertIn("Dias com snapshots: 3",msg)

    def test_owner_exclusivo(self):
        s=snapshot(22)
        write(self.path,[s])
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=23
        bot.username=None
        bot.previsoes=SimpleNamespace(path=self.path.with_name("previsoes_premium.json"),dados={"previsoes":[]})
        bot.enviar_mensagem=Mock()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP proibido")):
            bot.processar_comando(24,"/lambda_validacao",user_id=24)
            bot.processar_comando(23,"/lambda_validacao",user_id=24)
            bot.enviar_mensagem.assert_not_called()
            bot.processar_comando(23,"/lambda_validacao",user_id=23)
            bot.enviar_mensagem.assert_called_once()
            self.assertIn("LAMBDA VALIDAÇÃO FUTURA",bot.enviar_mensagem.call_args.args[1])


if __name__=="__main__":
    unittest.main()
