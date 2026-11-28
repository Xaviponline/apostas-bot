"""Regressão para auditoria Lambda emparelhada, só leitura e determinística."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from lambda_robustez_shadow import _jogos_emparelhados, _intervalo_clusters, relatorio_lambda_robustez
from main_competicoes import BotPremiumDiarioCompeticoes

MER = ("Vitória Casa", "Empate", "Vitória Fora")


def snapshot(jid, liga="eng.2", delta_days=0, capture_offset=-60, a=(.6,.2,.2), b=(.7,.2,.1)):
    ini=datetime(2026,11,20,19,tzinfo=timezone.utc)+timedelta(days=delta_days)
    ts=ini.timestamp()
    return {
        "versao":1,"capturado_em_utc":(ini+timedelta(minutes=capture_offset)).isoformat(),
        "liga_codigo":liga,"chave":f"{liga}-{jid}-{ts}",
        "jogo":{"id":jid,"casa_id":jid+100,"fora_id":jid+200,"timestamp":ts},
        "original_1x2":dict(zip(MER,a)),"alternativa_1x2":dict(zip(MER,b)),
    }


def final(reg, score=(2,0)):
    return {"chave":reg["chave"],"jogo":reg["jogo"],"liga_codigo":reg["liga_codigo"],
            "golos_casa":score[0],"golos_fora":score[1], "fonte":"ESPN_STATUS_FINAL"}


def write(path,rows):
    path.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8")


class LambdaRobustezTest(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.path=Path(td.name)/"lambda_prospectivo_shadow.jsonl"
        self.res=self.path.with_name("lambda_prospectivo_resultados.jsonl")

    def test_sem_ficheiro(self):
        self.assertIn("Sem snapshots Lambda",relatorio_lambda_robustez(self.path))

    def test_sem_api_sem_escrita_emparelhado_e_ic_reprodutivel(self):
        x=snapshot(1,liga="ita.2")
        y=snapshot(2,liga="eng.2",delta_days=1,b=(.4,.1,.5))
        z=snapshot(3,liga="bra.1",delta_days=2)
        write(self.path,[x,y,z])
        write(self.res,[final(x),final(y,score=(1,1)),final(z)])
        b0=self.path.read_bytes(),self.res.read_bytes()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP proibido")):
            msg=relatorio_lambda_robustez(self.path)
            msg2=relatorio_lambda_robustez(self.path)
        self.assertEqual(msg,msg2)
        self.assertIn("Jogos pré-jogo com final ESPN independente exato: 3",msg)
        self.assertIn("Jogo a jogo: alternativa melhor 2 | pior 1 | igual 0",msg)
        self.assertIn("bootstrap dia×liga, 3 grupos",msg)
        self.assertIn("bootstrap, 3 dias",msg)
        self.assertIn("sem eng.2 (n=1)",msg)
        self.assertEqual(b0,(self.path.read_bytes(),self.res.read_bytes()))

    def test_identidade_conflitos_captura_repetidos_e_sem_espn(self):
        ok=snapshot(1)
        pos=snapshot(2,capture_offset=3)
        sem=snapshot(3)
        confl=snapshot(4)
        errado=snapshot(5)
        sem["original_1x2"]={**sem["original_1x2"],"Empate":float("nan")}
        extra=snapshot(6)
        write(self.path,[ok,pos,confl,errado,sem,extra,ok])
        wrong=final(errado)
        wrong["jogo"]={**wrong["jogo"],"timestamp":wrong["jogo"]["timestamp"]+60}
        write(self.res,[final(ok),final(pos),final(confl),final(confl,score=(1,1)),wrong])
        dados,motivos=_jogos_emparelhados(self.path)
        self.assertEqual(len(dados),1)
        self.assertEqual(motivos["duplicado"],1)
        self.assertEqual(motivos["nao_pre_jogo"],1)
        self.assertEqual(motivos["final_conflitante"],1)
        self.assertEqual(motivos["sem_final_espn"],2)
        self.assertEqual(motivos["vetor_invalido"],1)

    def test_poucos_clusters_sem_intervalo_inventado(self):
        one=snapshot(101)
        two=snapshot(102)
        write(self.path,[one,two])
        write(self.res,[final(one),final(two)])
        msg=relatorio_lambda_robustez(self.path)
        self.assertIn("Grupos insuficientes para um dos intervalos",msg)
        self.assertNotIn("IC exploratório 95%",msg)

    def test_ic_delimitado_quando_delta_constante(self):
        j=[{"delta":-.01,"dia":f"2026-11-{20+i:02d}","liga":"eng.2"} for i in range(7)]
        ci,n=_intervalo_clusters(j,lambda x: x["dia"])
        self.assertEqual(n,7)
        self.assertAlmostEqual(ci[0],-.01)
        self.assertAlmostEqual(ci[1],-.01)

    def test_owner_exclusivo(self):
        s=snapshot(111)
        write(self.path,[s])
        write(self.res,[final(s)])
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=23
        bot.username=None
        bot.previsoes=SimpleNamespace(path=self.path.with_name("previsoes_premium.json"), dados={"previsoes":[]})
        bot.enviar_mensagem=Mock()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP proibido")):
            bot.processar_comando(24,"/lambda_robustez",user_id=24)
            bot.processar_comando(23,"/lambda_robustez",user_id=24)
            bot.enviar_mensagem.assert_not_called()
            bot.processar_comando(23,"/lambda_robustez",user_id=23)
            bot.enviar_mensagem.assert_called_once()
            self.assertIn("LAMBDA ROBUSTEZ", bot.enviar_mensagem.call_args.args[1])


if __name__=="__main__":
    unittest.main()
