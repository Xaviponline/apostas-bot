"""Cobertura dos resultados Lambda, sem HTTP nem mutação."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lambda_cobertura_shadow import relatorio_lambda_cobertura
from main_competicoes import BotPremiumDiarioCompeticoes

AGORA=datetime(2026,11,27,21,0,tzinfo=timezone.utc)
INI=AGORA - timedelta(hours=3)
MER=("Vitória Casa","Empate","Vitória Fora")


def r(jid, capture=None, ts=None, liga="eng.2"):
    ts = ts or INI
    capture = capture if capture is not None else (ts-timedelta(hours=1))
    jogo={
        "id":jid,"casa_id":jid+10000,"fora_id":jid+20000,
        "timestamp":ts.timestamp(),
    }
    chave=f"{liga}|{jid}|{ts.timestamp()}|{jid+10000}|{jid+20000}|{liga}"
    return {
        "versao":1,"capturado_em_utc":capture.isoformat(),
        "liga_codigo":liga,"chave":chave,"jogo":jogo,
        "original_1x2":{"Vitória Casa":.5,"Empate":.3,"Vitória Fora":.2},
        "alternativa_1x2":{"Vitória Casa":.4,"Empate":.3,"Vitória Fora":.3},
    }


def final(reg, gc=2, gf=1):
    return {
        "chave":reg["chave"],"liga_codigo":reg["liga_codigo"],
        "jogo":reg["jogo"],"golos_casa":gc,"golos_fora":gf,
        "fonte":"ESPN_STATUS_FINAL",
    }


def oficial(jid, gc=2, gf=1):
    return {"event_id":jid,"golos_casa":gc,"golos_fora":gf,"resultado_binario":1}


def gravar(path, entradas):
    path.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in entradas),encoding="utf-8")


class LambdaCoberturaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"lambda_prospectivo_shadow.jsonl"
        self.res=self.path.with_name("lambda_prospectivo_resultados.jsonl")

    def test_sobreposicao_id_estrito_sem_resultado_e_pregame(self):
        a,b,c,d,e = [r(i) for i in range(1,6)]
        e["capturado_em_utc"]=(INI+timedelta(minutes=1)).isoformat()  # pós-kickoff
        f=r(6,ts=AGORA+timedelta(days=1))
        gravar(self.path,[a,b,c,d,e,f,a])
        gravar(self.res,[final(a),final(c)])
        dados={"previsoes":[oficial(1),oficial(2),oficial(5)]}
        antes=copy.deepcopy(dados)
        texto=relatorio_lambda_cobertura(self.path,dados,agora=AGORA)
        for esperado in (
            "Registos V1 com vetores 1X2 válidos: 7",
            "identidade incompleta: 0 | duplicadas: 1",
            "Captura pré-jogo comprovada: 5 | não comprovada/fora do prazo: 1",
            "4 jogos já iniciados | 1 por iniciar",
            "histórico oficial por ID do evento: 2",
            "ESPN independente por IDs+liga+horário+chave: 2",
            "Sobreposição entre ambos: 1",
            "Placares discordantes na sobreposição: 0",
            "Sem resultado em nenhuma das duas fontes: 2",
            "eng.2 (2)",
        ):
            self.assertIn(esperado,texto,esperado)
        self.assertEqual(dados,antes)

    def test_identidade_invalida_e_captura_ausente_nao_geram_resultado(self):
        a=r(10); a["jogo"]["casa_id"]=None
        b=r(11); b["capturado_em_utc"]="2026-11-27T18:00:00"  # sem timezone
        c=r(12); c["original_1x2"]["Vitória Casa"]=float("nan")
        gravar(self.path,[a,b,c])
        texto=relatorio_lambda_cobertura(self.path,{"previsoes":[]},agora=AGORA)
        self.assertIn("Registos V1 com vetores 1X2 válidos: 2",texto)
        self.assertIn("Linhas inválidas/sem vetor: 1",texto)
        self.assertIn("identidade incompleta: 1",texto)
        self.assertIn("não comprovada/fora do prazo: 1",texto)
        self.assertIn("Sem resultado em nenhuma das duas fontes: 0",texto)

    def test_placares_contraditorios_na_sobreposicao_sao_visiveis(self):
        a=r(20)
        gravar(self.path,[a])
        gravar(self.res,[final(a,2,1)])
        texto=relatorio_lambda_cobertura(self.path,{"previsoes":[oficial(20,1,2)]},agora=AGORA)
        self.assertIn("Sobreposição entre ambos: 1",texto)
        self.assertIn("Placares discordantes na sobreposição: 1",texto)

    def test_conflito_independente_nao_aceite_como_confirmacao(self):
        a=r(30)
        gravar(self.path,[a])
        gravar(self.res,[final(a,2,1),final(a,1,2)])
        texto=relatorio_lambda_cobertura(self.path,{"previsoes":[]},agora=AGORA)
        self.assertIn("ESPN independente por IDs+liga+horário+chave: 0",texto)
        self.assertIn("Sem resultado em nenhuma das duas fontes: 1",texto)

    def test_sem_ficheiro_shadows_nada_inventa(self):
        texto=relatorio_lambda_cobertura(self.path,{"previsoes":[]},agora=AGORA)
        self.assertIn("Ficheiro prospetivo não disponível",texto)

    def test_owner_only_e_sem_http_ou_escrita(self):
        p=r(50);gravar(self.path,[p])
        dados={"previsoes":[oficial(50)]}
        reg=SimpleNamespace(path=self.path.with_name("previsoes_premium.json"),dados=dados)
        bot=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        bot.owner_id=bot.chat_id=13
        bot.username=None
        bot.previsoes=reg
        bot.enviar_mensagem=Mock()
        original=self.path.read_bytes()
        with patch("requests.sessions.Session.get",side_effect=AssertionError("HTTP proibido")), \
             patch("lambda_cobertura_shadow.Path.write_text",side_effect=AssertionError("Escrita proibida")):
            bot.processar_comando(14,"/lambda_cobertura",user_id=14)
            bot.processar_comando(13,"/lambda_cobertura",user_id=14)
            bot.enviar_mensagem.assert_not_called()
            bot.processar_comando(13,"/lambda_cobertura",user_id=13)
            bot.enviar_mensagem.assert_called_once()
            self.assertIn("LAMBDA COBERTURA",bot.enviar_mensagem.call_args.args[1])
        self.assertEqual(self.path.read_bytes(),original)


if __name__=="__main__":
    unittest.main()
