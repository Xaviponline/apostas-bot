"""Testes da telemetria passiva do descobrimento OddsPapi.

A informação NÃO permite associar fixtures, odds ou alterar picks.
"""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from odds_auditoria import AuditoriaOdds
from odds_rastreio import RastreioOdds
from odds_falhas_shadow import gerar_painel_falhas

PT = ZoneInfo("Europe/Lisbon")
AGORA = datetime(2030, 10, 16, 15, tzinfo=PT)
TS = datetime(2030, 10, 16, 18, tzinfo=PT).timestamp()


def selecao():
    return {
        "jogo": {
            "id": 202, "casa": "Ponte Preta", "fora": "Atlético Goianiense",
            "liga": "Brasileiro Serie B", "timestamp": TS,
        },
        "mercado": "Under 2.5 Golos", "probabilidade": 0.68,
        "odd_minima": 1.51,
    }


def snapshot():
    return {
        "data_jogo": "2030-10-16", "modelo_versao": "V1.2",
        "ranking_modelo": 3, "event_id": 202,
        "timestamp_jogo": TS, "casa": "Ponte Preta",
        "fora": "Atlético Goianiense", "liga": "Brasileiro Serie B",
        "mercado": "Under 2.5 Golos", "odd_minima": 1.51,
        "odd_real": None,
    }


def evento(eid, casa, fora):
    return {"id": eid, "casa": casa, "fora": fora,
            "data": "2030-10-16T17:00:00Z", "liga": "Brasileiro Serie B"}


class FonteSomenteDescoberta:
    configurada = True
    nome_fonte = "OddsPapi Fake"
    def __init__(self):
        self.principal_chamadas = 0
        self.complementar_chamadas = 0
        self.odds_chamadas = 0

    def eventos_hoje(self):
        self.principal_chamadas += 1
        return [
            evento("casa", "Ponte Preta", "Outra Equipa"),
            evento("fora", "Outra Equipa", "Atletico Goianiense"),
            evento("invertido", "Atletico Goianiense", "Ponte Preta"),
        ]

    def eventos_complementares(self):
        self.complementar_chamadas += 1
        return [evento("comp", "Ponte Preta", "Mais Um Adversário")]

    def odds_evento(self, eid):
        self.odds_chamadas += 1
        raise AssertionError("Nunca consultar odds sem fixture validado")


class PistasDescobertaTests(unittest.TestCase):
    def test_pistas_primario_e_complementar_sem_criar_fixture_ou_consumo(self):
        fonte = FonteSomenteDescoberta()
        original = selecao()
        antes = copy.deepcopy(original)
        saida = AuditoriaOdds(fonte).enriquecer(
            [original], fallback_individual_ausentes=True
        )
        self.assertEqual(original, antes)
        self.assertEqual(len(saida), 1)
        s = saida[0]
        self.assertEqual(s["_odds_diag"], "evento_nao_encontrado")
        self.assertNotIn("odd_real", s)
        self.assertNotIn("odds_event_id", s)
        self.assertEqual(fonte.principal_chamadas, 1)
        self.assertEqual(fonte.complementar_chamadas, 1)
        self.assertEqual(fonte.odds_chamadas, 0)
        pistas = s["_odds_descoberta"]
        self.assertEqual(pistas["primarios_vistos"], 3)
        self.assertEqual(pistas["complementares_vistos"], 1)
        self.assertTrue(pistas["complementar_consultada"])
        self.assertTrue(pistas["casa_primaria"])
        self.assertTrue(pistas["fora_primaria"])
        self.assertTrue(pistas["casa_complementar"])
        self.assertFalse(pistas["fora_complementar"])
        self.assertTrue(pistas["par_invertido"])
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "odds_rastreio.jsonl"
            RastreioOdds(destino).registar(saida)
            bruto = destino.read_bytes()
            linha = json.loads(bruto.decode().splitlines()[0])
            self.assertEqual(linha["descoberta_passiva"], pistas)
            painel = gerar_painel_falhas([snapshot()], destino, "3", agora=AGORA)
            self.assertIn("Eventos na listagem principal: 3", painel)
            self.assertIn("Consulta complementar: efetuada", painel)
            self.assertIn("Eventos adicionais integrados: 1", painel)
            self.assertIn("casa sim | fora sim", painel)
            self.assertIn("Nomes compatíveis em ordem invertida", painel)
            self.assertIn("não comprova evento", painel)
            self.assertIn("sem confirmação no snapshot", painel)
            self.assertEqual(destino.read_bytes(), bruto)

    def test_analise_normal_nao_faz_chamada_complementar(self):
        fonte = FonteSomenteDescoberta()
        entrada = selecao()
        saida = AuditoriaOdds(fonte).enriquecer([entrada])
        self.assertEqual(saida[0]["_odds_diag"], "evento_nao_encontrado")
        self.assertFalse(saida[0]["_odds_descoberta"]["complementar_consultada"])
        self.assertEqual(saida[0]["_odds_descoberta"]["complementares_vistos"], 0)
        self.assertEqual(fonte.principal_chamadas, 1)
        self.assertEqual(fonte.complementar_chamadas, 0)
        self.assertEqual(fonte.odds_chamadas, 0)

    def test_rastreio_sanitiza_pistas_e_nao_guarda_campos_arbitrarios(self):
        s = selecao()
        s["_odds_diag"] = "evento_nao_encontrado"
        s["_odds_descoberta"] = {
            "versao": 1, "primarios_vistos": 25, "complementares_vistos": 2,
            "casa_primaria": True, "fora_primaria": True,
            "par_invertido": True, "complementar_consultada": True,
            "apiKey": "SEGREDO_NAO_GUARDAR",
            "url": "https://irrelevante.invalid/segredo",
        }
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "rastreio.jsonl"
            RastreioOdds(destino).registar([s])
            txt = destino.read_text()
            self.assertNotIn("SEGREDO_NAO_GUARDAR", txt)
            self.assertNotIn("irrelevante.invalid", txt)
            r = json.loads(txt)
            self.assertEqual(r["descoberta_passiva"]["primarios_vistos"], 25)
            self.assertEqual(r["descoberta_passiva"]["complementares_vistos"], 2)

    def test_painel_historico_antes_da_instrumentacao_nao_inventa_pistas(self):
        s = selecao()
        s["_odds_diag"] = "evento_nao_encontrado"
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "odds_rastreio.jsonl"
            RastreioOdds(destino).registar([s])
            t = gerar_painel_falhas([snapshot()], destino, "3", agora=AGORA)
            self.assertIn("não é possível reconstituir o passado", t)
            self.assertNotIn("Eventos na listagem principal:", t)


if __name__ == "__main__":
    unittest.main()
