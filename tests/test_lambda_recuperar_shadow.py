"""Regressão recuperação histórica ESPN apenas quando explicitamente executada."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lambda_recuperar_shadow import relatorio_lambda_recuperar
from main_competicoes import BotPremiumDiarioCompeticoes

AGORA = datetime(2026, 11, 27, 21, tzinfo=timezone.utc)
MERCADOS = ("Vitória Casa", "Empate", "Vitória Fora")


def snapshot(eid, dia=5, liga="eng.2", created=None):
    inicio = datetime(2026, 11, dia, 18, tzinfo=timezone.utc)
    criado = created if created is not None else inicio - timedelta(hours=5)
    k = {
        "id":eid, "casa_id":eid+10000, "fora_id":eid+20000,
        "timestamp":inicio.timestamp(),
    }
    chave=f"{liga}|{eid}|{inicio.timestamp()}|{eid+10000}|{eid+20000}|{liga}"
    return {
        "versao":1, "capturado_em_utc":criado.isoformat(),
        "liga_codigo":liga, "chave":chave, "jogo":k,
        "original_1x2":{"Vitória Casa":.5,"Empate":.3,"Vitória Fora":.2},
        "alternativa_1x2":{"Vitória Casa":.4,"Empate":.3,"Vitória Fora":.3},
    }


def espn(reg,*,final=True,ts_delta=0,home_id=None,score=(2,1)):
    j=reg["jogo"]
    inicio=datetime.fromtimestamp(j["timestamp"]+ts_delta,timezone.utc)
    return {
        "id":str(j["id"]),
        "date":inicio.isoformat().replace("+00:00","Z"),
        "status":{"type":{
            "name":"STATUS_FULL_TIME" if final else "STATUS_IN_PROGRESS",
            "state":"post" if final else "in",
            "completed":bool(final),
            "detail":"FT" if final else "Live",
        }},
        "competitions":[{
            "competitors":[
                {"homeAway":"home","team":{"id":str(home_id or j["casa_id"]),"displayName":"Casa"},"score":str(score[0])},
                {"homeAway":"away","team":{"id":str(j["fora_id"]),"displayName":"Fora"},"score":str(score[1])},
            ]
        }],
    }


class Resposta:
    def __init__(self,eventos):
        self.eventos=eventos
    def raise_for_status(self):pass
    def json(self):return {"events":self.eventos}


class Cliente:
    def __init__(self,dict_ev):
        self.data=dict_ev
        self.calls=[]
    def get(self,url,params,timeout):
        self.calls.append((url,dict(params),timeout))
        return Resposta(self.data.get((url.rsplit("/",2)[-2],params["dates"]), []))


def gravar(path,rows):
    path.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")


class RecuperarHistoricoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"lambda_prospectivo_shadow.jsonl"
        self.res=self.path.with_name("lambda_prospectivo_resultados.jsonl")

    def test_preview_zero_http_zero_escrita_e_data_mais_recente_primeiro(self):
        a,b=snapshot(1,dia=5),snapshot(2,dia=6)
        gravar(self.path,[a,b])
        original=self.path.read_bytes()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP em preview")), \
             patch("lambda_recuperar_shadow.guardar_resultados",side_effect=AssertionError("write em preview")):
            msg=relatorio_lambda_recuperar(self.path,agora=AGORA)
        for frag in ("Grupos dia×liga: 2 | página 1/1",
                     "Registos sem confirmação ESPN exata: 2",
                     "2026-11-06 eng.2: 1 snapshots | sem ESPN exata 1",
                     "2026-11-05 eng.2: 1 snapshots | sem ESPN exata 1",
                     "Esta página exigiria 2 consultas públicas ESPN",
                     "PRÉ-VISUALIZAÇÃO: zero HTTP, zero escrita",
                     "/lambda_recuperar executar 1"):
            self.assertIn(frag,msg)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertFalse(self.res.exists())

    def test_execucao_explicitamente_autorizada_guarda_apenas_finais_exatos(self):
        a,b=snapshot(101,dia=5),snapshot(102,dia=6)
        gravar(self.path,[a,b])
        eventos={
            ("eng.2","20261105"):[espn(a)],
            ("eng.2","20261106"):[espn(b)],
        }
        cliente=Cliente(eventos)
        anterior=self.path.read_bytes()
        msg=relatorio_lambda_recuperar(self.path,"executar 1",agora=AGORA,session=cliente)
        self.assertEqual(len(cliente.calls),2)
        self.assertTrue(all(c[0].startswith("https://site.api.espn.com/apis/site/v2/sports/soccer/eng.2/scoreboard") for c in cliente.calls))
        self.assertIn("Novos resultados SHADOW guardados: 2",msg)
        self.assertEqual(self.path.read_bytes(),anterior)
        finais=[json.loads(l) for l in self.res.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(finais),2)
        self.assertTrue(all(x["fonte"]=="ESPN_STATUS_FINAL" for x in finais))
        self.assertEqual({x["golos_casa"] for x in finais},{2})
        msg2=relatorio_lambda_recuperar(self.path,"executar 1",agora=AGORA,session=cliente)
        self.assertIn("Novos resultados SHADOW guardados: 0",msg2)
        self.assertEqual(len(cliente.calls),2) # Sem grupos pendentes, sem HTTP

    def test_recusa_horario_divergente_nomes_nao_chegam(self):
        a=snapshot(201,dia=5)
        gravar(self.path,[a])
        cliente=Cliente({("eng.2","20261105"):[espn(a,ts_delta=3600)]})
        msg=relatorio_lambda_recuperar(self.path,"executar 1",agora=AGORA,session=cliente)
        self.assertIn("horários ≠ 1",msg)
        self.assertIn("Novos resultados SHADOW guardados: 0",msg)
        self.assertFalse(self.res.exists())

    def test_recusa_equipa_id_divergente_e_pendente(self):
        a=snapshot(202,dia=5)
        gravar(self.path,[a])
        cliente=Cliente({("eng.2","20261105"):[espn(a,home_id=44444)]})
        msg=relatorio_lambda_recuperar(self.path,"executar 1",agora=AGORA,session=cliente)
        self.assertIn("equipas ≠ 1",msg)
        self.assertFalse(self.res.exists())
        cliente=Cliente({("eng.2","20261105"):[espn(a,final=False)]})
        msg=relatorio_lambda_recuperar(self.path,"executar 1",agora=AGORA,session=cliente)
        self.assertIn("sem final regular 1",msg)
        self.assertFalse(self.res.exists())

    def test_teto_seis_e_paginas_estaveis_apos_gravacao(self):
        rows=[snapshot(i,dia=i) for i in range(1,8)]
        gravar(self.path,rows)
        t1=relatorio_lambda_recuperar(self.path,"1",agora=AGORA)
        t2=relatorio_lambda_recuperar(self.path,"2",agora=AGORA)
        self.assertIn("página 1/2",t1)
        self.assertIn("página 2/2",t2)
        self.assertIn("2026-11-01 eng.2",t2)
        self.assertNotIn("2026-11-07 eng.2",t2)
        m1={("eng.2",f"202611{i:02d}"):[espn(rows[i-1])] for i in range(2,8)}
        cliente=Cliente(m1)
        msg=relatorio_lambda_recuperar(self.path,"executar 1",agora=AGORA,session=cliente)
        self.assertEqual(len(cliente.calls),6)
        self.assertIn("Novos resultados SHADOW guardados: 6",msg)
        t2b=relatorio_lambda_recuperar(self.path,"2",agora=AGORA)
        self.assertIn("2026-11-01 eng.2",t2b)
        self.assertIn("sem ESPN exata 1",t2b)

    def test_nao_consulta_futuros_tardios_e_sem_captura_prejogo(self):
        a=snapshot(501,dia=5)
        b=snapshot(502,dia=28)  # Futuro
        c=snapshot(503,dia=6)
        c["capturado_em_utc"]=(datetime.fromtimestamp(c["jogo"]["timestamp"],timezone.utc)+timedelta(minutes=1)).isoformat()
        gravar(self.path,[a,b,c])
        msg=relatorio_lambda_recuperar(self.path,agora=AGORA)
        self.assertIn("Grupos dia×liga: 1",msg)
        self.assertIn("captura_invalida=1",msg)
        self.assertIn("recente_ou_futuro=1",msg)
        self.assertIn("Registos sem confirmação ESPN exata: 1",msg)

    def test_argumento_invalido_e_pagina_inexistente_sem_http(self):
        gravar(self.path,[snapshot(601,dia=5)])
        for entrada in ("executar","executar 0","0","-1","1.0","todo","executar -3","executar 1;ls"):
            self.assertIn("Uso: /lambda_recuperar",relatorio_lambda_recuperar(self.path,entrada,agora=AGORA))
        self.assertIn("Página 2 inexistente",relatorio_lambda_recuperar(self.path,"2",agora=AGORA))

    def test_sem_registos_nao_inventa(self):
        self.assertIn("sem snapshots prospetivos",relatorio_lambda_recuperar(self.path,agora=AGORA))

    def test_owner_exclusivo_preview_sem_apis(self):
        gravar(self.path,[snapshot(701,dia=5)])
        b=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id=b.chat_id=23
        b.username=None
        b.previsoes=SimpleNamespace(path=self.path.with_name("previsoes_premium.json"),dados={"previsoes":[]})
        b.enviar_mensagem=Mock()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP preview não permitido")):
            b.processar_comando(24,"/lambda_recuperar",user_id=24)
            b.processar_comando(23,"/lambda_recuperar",user_id=24)
            b.enviar_mensagem.assert_not_called()
            b.processar_comando(23,"/lambda_recuperar",user_id=23)
            b.enviar_mensagem.assert_called_once()
            self.assertIn("PRÉ-VISUALIZAÇÃO",b.enviar_mensagem.call_args.args[1])


if __name__=="__main__":
    unittest.main()
