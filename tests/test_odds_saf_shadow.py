"""Regressão SHADOW: variante legal SAF nunca associa automaticamente fixtures.

Zero pedidos extra, zero alteração de odds, V1.2, SEL1 ou V1.3.
"""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds
from odds_falhas_shadow import gerar_painel_falhas
from odds_rastreio import RastreioOdds


TZ = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 16, 15, tzinfo=TZ)
TS = datetime(2030, 10, 16, 18, tzinfo=TZ).timestamp()


def evento(eid, casa, fora, data="2030-10-16T17:00:00Z"):
    return {"id": eid, "casa": casa, "fora": fora, "data": data,
            "liga": "Brasileiro Serie B"}


def selecao():
    return {
        "jogo": {"id": 303, "casa": "Ponte Preta",
                 "fora": "Atlético Goianiense", "timestamp": TS,
                 "liga": "Brasileiro Serie B"},
        "mercado": "Under 2.5 Golos",
        "probabilidade": 0.68, "odd_minima": 1.51,
    }


def snapshot():
    return {
        "data_jogo": "2030-10-16", "modelo_versao": "V1.2",
        "ranking_modelo": 3, "event_id": 303, "timestamp_jogo": TS,
        "casa": "Ponte Preta", "fora": "Atlético Goianiense",
        "liga": "Brasileiro Serie B", "mercado": "Under 2.5 Golos",
        "odd_minima": 1.51, "odd_real": None,
    }


class FonteMock:
    configurada = True
    nome_fonte = "OddsPapi test"

    def __init__(self, primarios, extras=()):
        self.primarios = list(primarios)
        self.extras = list(extras)
        self.contagem_principal = 0
        self.contagem_extra = 0
        self.contagem_odds = 0

    def eventos_hoje(self):
        self.contagem_principal += 1
        return list(self.primarios)

    def eventos_complementares(self):
        self.contagem_extra += 1
        return list(self.extras)

    def odds_evento(self, event_id):
        self.contagem_odds += 1
        raise AssertionError("Nao e seguro consultar odds de um candidato SAF")


class SAFShadowTests(unittest.TestCase):
    def test_saf_par_possivel_hora_certa_sem_associacao_ou_odd(self):
        fonte = FonteMock([
            evento("saf1", "Ponte Preta", "Atlético Goianiense SAF")
        ])
        original = selecao()
        anterior = copy.deepcopy(original)
        saida = AuditoriaOdds(fonte).enriquecer([original])
        self.assertEqual(original, anterior)
        self.assertEqual(fonte.contagem_principal, 1)
        self.assertEqual(fonte.contagem_extra, 0)
        self.assertEqual(fonte.contagem_odds, 0)
        self.assertEqual(saida[0]["_odds_diag"], "evento_nao_encontrado")
        self.assertNotIn("odd_real", saida[0])
        self.assertNotIn("odds_event_id", saida[0])
        pistas = saida[0]["_odds_descoberta"]
        self.assertTrue(pistas["saf_testado"])
        self.assertFalse(pistas["fora_primaria"])
        self.assertTrue(pistas["saf_fora_primaria"])
        self.assertEqual(pistas["saf_par_primario"], 1)
        self.assertEqual(pistas["saf_par_hora_compativel"], 1)
        self.assertEqual(pistas["saf_par_hora_divergente"], 0)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "odds_rastreio.jsonl"
            hist = RastreioOdds(caminho)
            hist.registar(saida)
            bruto = caminho.read_bytes()
            reg = json.loads(bruto)
            self.assertEqual(reg["descoberta_passiva"], pistas)
            painel = gerar_painel_falhas([snapshot()], caminho, "3", agora=AGORA)
            self.assertIn("Variante SAF na lista principal: casa não | fora sim", painel)
            self.assertIn("Possíveis pares com variante SAF: principal 1, complementar 0", painel)
            self.assertIn("Horário dos possíveis pares: compatível 1, divergente 0", painel)
            self.assertIn("SAF é só uma hipótese de nomenclatura", painel)
            self.assertIn("sem confirmação no snapshot", painel)
            self.assertEqual(caminho.read_bytes(), bruto)

    def test_saf_equipas_separadas_nao_cria_par(self):
        fonte = FonteMock([
            evento("casa", "Ponte Preta", "Outro Clube"),
            evento("fora", "Outro Clube", "Atlético Goianiense SAF"),
        ])
        s = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        pistas = s["_odds_descoberta"]
        self.assertEqual(s["_odds_diag"], "evento_nao_encontrado")
        self.assertTrue(pistas["casa_primaria"])
        self.assertTrue(pistas["saf_fora_primaria"])
        self.assertEqual(pistas["saf_par_primario"], 0)
        self.assertEqual(fonte.contagem_odds, 0)

    def test_saf_par_horario_divergente_nao_associa(self):
        fonte = FonteMock([
            evento("saf-hora", "Ponte Preta", "Atletico GO SAF", "2030-10-16T20:00:00Z")
        ])
        s = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        pistas = s["_odds_descoberta"]
        self.assertEqual(pistas["saf_par_primario"], 1)
        self.assertEqual(pistas["saf_par_hora_divergente"], 1)
        self.assertEqual(pistas["saf_par_hora_compativel"], 0)
        self.assertNotIn("odds_event_id", s)
        self.assertEqual(fonte.contagem_odds, 0)

    def test_saf_par_hora_indisponivel_nao_associa(self):
        fonte = FonteMock([evento("saf-empty", "Ponte Preta", "Atletico GO SAF", "")])
        s = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
        self.assertEqual(s["_odds_descoberta"]["saf_par_hora_desconhecida"], 1)
        self.assertEqual(fonte.contagem_odds, 0)

    def test_saf_nao_e_fuzzy_nem_qualquer_sufixo(self):
        for nome in (
            "Atlético Goianiense SAF Sub-20", "Athletico Goianiense SAF",
            "Atlético Mineiro SAF", "Goianiense SAF", "Atlético Goianiense SC",
        ):
            with self.subTest(nome=nome):
                fonte = FonteMock([evento("outro", "Ponte Preta", nome)])
                s = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
                pistas = s["_odds_descoberta"]
                self.assertEqual(pistas["saf_par_primario"], 0)
                self.assertFalse(pistas["saf_fora_primaria"])
                self.assertEqual(fonte.contagem_odds, 0)

    def test_complementar_e_historico_antigo_nao_sao_inventados(self):
        fonte = FonteMock(
            [evento("normal", "Ponte Preta", "Outra Equipa")],
            [evento("saf2", "Ponte Preta", "Atlético Goianiense SAF")],
        )
        atual = AuditoriaOdds(fonte).enriquecer([selecao()], fallback_individual_ausentes=True)
        pistas = atual[0]["_odds_descoberta"]
        self.assertEqual(pistas["saf_par_primario"], 0)
        self.assertEqual(pistas["saf_par_complementar"], 1)
        self.assertEqual(fonte.contagem_extra, 1)
        self.assertEqual(fonte.contagem_odds, 0)
        passado = selecao()
        passado["_odds_diag"] = "evento_nao_encontrado"
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "odds_rastreio.jsonl"
            RastreioOdds(caminho).registar([passado])
            antigo = gerar_painel_falhas([snapshot()], caminho, "3", agora=AGORA)
            self.assertNotIn("SAF (sufixo exato)", antigo)


if __name__ == "__main__":
    unittest.main()
