"""Prova do CLV oficial da coorte fixa V1.3 e comparação passiva com rastreio."""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from main_competicoes import BotPremiumDiarioCompeticoes
from odds_rastreio import RastreioOdds
from v13_prova_preco_shadow import relatorio_prova_preco_v13

PT = ZoneInfo("Europe/Lisbon")


class Registo:
    def __init__(self, c=None, p=None):
        self.dados = {"previsoes": [p or _previsao()]}
        self.c = c if c is not None else [_coorte()]
    def metricas_v13_comercial(self):
        return {"coorte": self.c}


def _previsao():
    return {
        "modelo_versao": "V1.2",
        "event_id": 401915394, "data_jogo": "2026-10-21",
        "timestamp_jogo": datetime(2026, 10, 21, 20, tzinfo=PT).timestamp(),
        "casa": "Aston Villa", "fora": "Viking FK",
        "liga": "UEFA Champions League", "mercado": "Under 3.5 Golos",
        "odd_real": 2.07, "odd_valor_confirmado": 2.07,
        "valor_confirmado_em": "2026-10-21T18:40:00Z",
        "odd_fecho": 2.07, "odd_fecho_capturada_em": "2026-10-21T19:40:00Z",
        "odd_mercado_atual": 2.02,
        "odd_mercado_atual_em": "2026-10-21T19:55:00Z",
        "odds_fonte": "OddsPapi / Betano PT",
        "odds_event_id": "id1000000774165962",
    }


def _coorte():
    return {
        "snapshot": 1, "mercado": "Under 3.5 Golos",
        "odd_entrada": 2.07, "odd_fecho": 2.07, "clv": 0.0,
    }


def _obs(hora, odd, market="Under 3.5 Golos", event="401915394",
         fixture="id1000000774165962"):
    return {
        "event_id_modelo": event,
        "mercado_modelo": market,
        "timestamp_jogo": _previsao()["timestamp_jogo"],
        "observado_em": f"2026-10-21T{hora}:00Z",
        "odd_observada": odd, "fixture_id_fonte": fixture,
        "mercado_nome_fonte": "Over Under Full Time",
        "linha_fonte": 3.5, "selecao_nome_fonte": "Under",
        "outcome_ref_fonte": "10303297139",
    }


class ProvaPrecoV13Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "odds_rastreio.jsonl"
        self.rastreio = RastreioOdds(self.path)
        self.registo = Registo()

    def gravar(self, *rows):
        with self.path.open("a", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x,ensure_ascii=False)+"\n")

    def test_compara_entrada_fecho_e_tracos_sem_reescrever_arquivo(self):
        self.gravar(_obs("18:40", 2.07), _obs("19:50", None),
                    _obs("19:55", 2.02), _obs("19:55", 1.80, "Over 2.5 Golos"),
                    _obs("19:55", 1.90, event="wrong"))
        before=self.path.read_bytes()
        src=copy.deepcopy(self.registo.dados)
        txt=relatorio_prova_preco_v13(self.registo, self.rastreio, "1")
        self.assertIn("Entrada coorte: @2,07",txt)
        self.assertIn("Fecho CLV: @2,07",txt)
        self.assertIn("CLV oficial: +0,00%",txt)
        self.assertIn("RASTREIO LOCAL DO MESMO EVENTO/MERCADO: 3",txt)
        self.assertIn("odd @2,02",txt)
        self.assertIn("odd @2,07",txt)
        self.assertNotIn("odd @1,80",txt)
        self.assertNotIn("odd @1,90",txt)
        self.assertIn("NÃO prova que fossem executáveis",txt)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.registo.dados,src)

    def test_zero_clv_nao_substitui_cotacao_posterior(self):
        self.gravar(_obs("19:55",2.02))
        txt=relatorio_prova_preco_v13(self.registo,self.rastreio,"1")
        self.assertIn("CLV oficial: +0,00%",txt)
        self.assertIn("odd @2,02",txt)
        self.assertIn("não substitui o campo odd_fecho",txt)

    def test_snapshot_nao_pertence_coorte(self):
        txt=relatorio_prova_preco_v13(self.registo,self.rastreio,"399")
        self.assertIn("não pertence à coorte fixa",txt)
        self.assertFalse(self.path.exists())

    def test_sem_rastreio_gera_prova_clv_oficial(self):
        txt=relatorio_prova_preco_v13(self.registo,self.rastreio,"1")
        self.assertIn("RASTREIO LOCAL DO MESMO EVENTO/MERCADO: 0",txt)
        self.assertIn("sem ficheiro",txt)
        self.assertIn("Fecho CLV: @2,07",txt)

    def test_sem_fecho_nao_inventa_clv(self):
        c=_coorte()
        c.update(odd_fecho=None,clv=None)
        reg=Registo(c=[c])
        txt=relatorio_prova_preco_v13(reg,self.rastreio,"1")
        self.assertIn("Fecho CLV: @não registada",txt)
        self.assertIn("CLV oficial: sem fecho",txt)

    def test_inconsistencia_clv_falha_fechado(self):
        c=_coorte()
        c["clv"] = .125
        with self.assertRaises(ValueError):
            relatorio_prova_preco_v13(Registo(c=[c]),self.rastreio,"1")

    def test_erro_mercado_diferente_falha_fechado(self):
        c=_coorte()
        c["mercado"]="Under 2.5 Golos"
        with self.assertRaises(ValueError):
            relatorio_prova_preco_v13(Registo(c=[c]),self.rastreio,"1")

    def test_corrompido_e_symlink_falham_sem_escrita(self):
        self.gravar(_obs("19:40",2.07))
        with self.path.open("a",encoding="utf-8") as f:
            f.write("not-json")
        antes=self.path.read_bytes()
        with self.assertRaises(ValueError):
            relatorio_prova_preco_v13(self.registo,self.rastreio,"1")
        self.assertEqual(self.path.read_bytes(),antes)
        self.path.unlink()
        origem=Path(self.tmp.name)/"origem.jsonl"
        origem.write_text(json.dumps(_obs("19:40",2.07))+"\n",encoding="utf-8")
        self.path.symlink_to(origem)
        with self.assertRaises(RuntimeError):
            relatorio_prova_preco_v13(self.registo,self.rastreio,"1")

    def test_formato_input_recusa_injecao_e_bool(self):
        for arg in ("", "abc", "-1", "399;rm", "1.0", "0", "1234567"):
            self.assertIn("Uso: /v13_prova_preco",relatorio_prova_preco_v13(self.registo,self.rastreio,arg))

    def test_so_owner_pode_consultar(self):
        b=BotPremiumDiarioCompeticoes.__new__(BotPremiumDiarioCompeticoes)
        b.owner_id=b.chat_id=43
        b.username=None
        b.previsoes=self.registo
        b._rastreio_odds=self.rastreio
        b.enviar_mensagem=Mock()
        b.processar_comando(44,"/v13_prova_preco 1",user_id=44)
        b.processar_comando(43,"/v13_prova_preco 1",user_id=44)
        b.enviar_mensagem.assert_not_called()
        b.processar_comando(43,"/v13_prova_preco 1",user_id=43)
        b.enviar_mensagem.assert_called_once()
        self.assertIn("PROVA DA ODD / CLV",b.enviar_mensagem.call_args.args[1])


if __name__=="__main__":
    unittest.main()
