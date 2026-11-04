"""Regressões dos horários divergentes; sem odds extra nem alteração de snapshot."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from odds_auditoria import AuditoriaOdds
from odds_horario_shadow import detalhe_horario_shadow, normalizar_detalhe_horario_shadow
from odds_verificacao import VerificacaoOdds

INICIO = datetime(2030, 11, 4, 15, tzinfo=timezone.utc)


class Fonte:
    provider = "oddspapi"
    configurada = True
    nome_fonte = "Fake"

    def __init__(self, inicio):
        self.inicio = inicio
        self.odds_calls = 0

    def eventos_hoje(self):
        return [{"id": "abc", "casa": "Arsenal", "fora": "Chelsea",
                 "data": self.inicio, "liga": "Premier League"}]

    def odds_evento(self, event_id):
        self.odds_calls += 1
        raise AssertionError("Nunca consultar odds do fixture rejeitado")

    def odds_eventos_em_lote(self, eventos):
        self.odds_calls += 1
        raise AssertionError("Nunca consultar lote do fixture rejeitado")


def selecao():
    return {"jogo": {"id": 1, "casa": "Arsenal", "fora": "Chelsea",
                     "liga": "Premier League", "timestamp": INICIO.timestamp()},
            "mercado": "Ambas Marcam", "probabilidade": 0.67,
            "odd_minima": 1.59}


class HorarioShadowTests(unittest.TestCase):
    def auditado(self, minutos):
        fonte = Fonte((INICIO + timedelta(minutes=minutos)).isoformat())
        original = selecao()
        copia = copy.deepcopy(original)
        result = AuditoriaOdds(fonte).enriquecer([original])[0]
        self.assertEqual(original, copia)
        self.assertEqual(fonte.odds_calls, 0)
        self.assertEqual(result["_odds_diag"], "horario_fixture_incompativel")
        self.assertIn("horario_divergente", result["_odds_alertas"])
        self.assertNotIn("odd_real", result)
        return result

    def test_deltas_positivos_e_negativos_nao_libertam_odds(self):
        for minutos in (31, -31, 60, -60, 120):
            with self.subTest(minutos=minutos):
                meta = self.auditado(minutos)["_odds_horario_shadow"]
                self.assertAlmostEqual(meta["desvio_min"], minutos)
                self.assertTrue(meta["modelo_utc"].endswith("Z"))
                self.assertTrue(meta["fornecedor_utc"].endswith("Z"))

    def test_persistencia_separada_e_relatorio_legivel(self):
        s = self.auditado(60)
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "odds_verificacao.json"
            reg = VerificacaoOdds(path)
            self.assertEqual(reg.registar([s]), 1)
            bruto = path.read_text(encoding="utf-8")
            self.assertIn('"horario_shadow"', bruto)
            self.assertNotIn("odd_real", bruto)
            self.assertNotIn("odds_event_id", bruto)
            detalhes = json.loads(bruto)
            aviso = next(iter(detalhes["observacoes"].values()))
            self.assertEqual(aviso["horario_shadow"]["desvio_min"], 60)
            texto = reg.relatorio(
                SimpleNamespace(dados={"previsoes": []}), agora=INICIO + timedelta(hours=2)
            )
            self.assertIn("Modelo PT: 04/11/2030 15:00 +0000", texto)
            self.assertIn("Fornecedor PT: 04/11/2030 16:00 +0000", texto)
            self.assertIn("Desvio fornecedor - modelo: +60 min", texto)
            self.assertIn("UTC modelo: 2030-11-04T15:00:00Z", texto)

    def test_avisos_antigos_nao_inventam_hora(self):
        s = selecao()
        s["_odds_alertas"] = ["horario_divergente"]
        with tempfile.TemporaryDirectory() as t:
            reg = VerificacaoOdds(Path(t) / "odds_verificacao.json")
            self.assertEqual(reg.registar([s]), 1)
            text = reg.relatorio(
                SimpleNamespace(dados={"previsoes": []}), agora=INICIO + timedelta(hours=2)
            )
            self.assertIn("Horarios detalhados nao registados", text)
            self.assertNotIn("UTC fornecedor:", text)

    def test_nao_persiste_injecoes_de_campos_externos(self):
        s = self.auditado(60)
        s["_odds_horario_shadow"].update({
            "fornecedor_pt": "SEGREDO", "api_key": "SEGREDO",
            "desvio_min": 999999,
        })
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "odds_verificacao.json"
            self.assertEqual(VerificacaoOdds(path).registar([s]), 1)
            texto = path.read_text(encoding="utf-8")
            self.assertNotIn("SEGREDO", texto)
            self.assertNotIn("999999", texto)
            self.assertIn('"desvio_min": 60.0', texto)

    def test_horas_ausentes_ou_naive_sem_pistas_falsas(self):
        for hora in (None, "", "2030-11-04T16:00:00", "invalido"):
            with self.subTest(hora=hora):
                fonte = Fonte(hora)
                r = AuditoriaOdds(fonte).enriquecer([selecao()])[0]
                self.assertEqual(fonte.odds_calls, 0)
                self.assertEqual(r["_odds_diag"], "horario_fixture_nao_comprovado")
                self.assertNotIn("_odds_horario_shadow", r)
        self.assertIsNone(detalhe_horario_shadow(None, INICIO.isoformat()))
        self.assertIsNone(detalhe_horario_shadow(float("nan"), INICIO.isoformat()))

    def test_limiar_30_minutos_inalterado(self):
        self.assertIsNone(detalhe_horario_shadow(
            INICIO.timestamp(), (INICIO + timedelta(minutes=30)).isoformat()))
        self.assertIsNotNone(detalhe_horario_shadow(
            INICIO.timestamp(), (INICIO + timedelta(minutes=31)).isoformat()))

    def test_fuso_portugal_verao_e_inverno(self):
        inverno = self.auditado(60)["_odds_horario_shadow"]
        verao = datetime(2030, 7, 4, 15, tzinfo=timezone.utc)
        summer = detalhe_horario_shadow(
            verao.timestamp(), (verao + timedelta(minutes=60)).isoformat())
        self.assertTrue(inverno["modelo_pt"].endswith("+0000"))
        self.assertTrue(summer["modelo_pt"].endswith("+0100"))

    def test_marcador_nao_pode_trocar_hora_do_modelo(self):
        meta = self.auditado(-60)["_odds_horario_shadow"]
        self.assertIsNone(normalizar_detalhe_horario_shadow(
            meta, INICIO.timestamp() + 60))
        self.assertEqual(normalizar_detalhe_horario_shadow(
            {**meta, "secreto": "nao copiar"}, INICIO.timestamp()), meta)


if __name__ == "__main__":
    unittest.main()
