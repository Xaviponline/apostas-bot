"""Regressoes: sem associar odds de outro fixture, categoria ou hora."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from odds_auditoria import AuditoriaOdds
from odds_identidade_guard import (
    classificar_frescura, equipas_categoria_incompativel, verificar_hora_fixture,
)
from odds_verificacao import VerificacaoOdds

START = datetime(2030, 10, 24, 15, tzinfo=timezone.utc)


class Fonte:
    configurada = True
    nome_fonte = "OddsPapi Teste"
    provider = "oddspapi"

    def __init__(self, hora=None, liga="English Premier League", odd_atualizada=None):
        self.hora = hora
        self.liga = liga
        self.odd_atualizada = odd_atualizada
        self.odds_calls = 0
        self.lote_calls = 0

    def eventos_hoje(self):
        return [{"id": "real_event", "casa": "Arsenal", "fora": "Chelsea",
                 "data": self.hora, "liga": self.liga, "tournament_id": 101}]

    def odds_eventos_em_lote(self, eventos):
        self.lote_calls += 1
        return {"real_event": self.odds_evento("real_event")}

    def odds_evento(self, event_id):
        self.odds_calls += 1
        row = {"seleção": "1", "odd": 1.85}
        if self.odd_atualizada is not None:
            row["changedAt"] = self.odd_atualizada
        return {"id": event_id, "casa": "Arsenal", "fora": "Chelsea",
                "liga": self.liga, "fonte": "OddsPapi Teste",
                "mercados": [{
                    "name": "Full Time Result", "period": "fulltime",
                    "odds": [row],
                }]}


def selecao():
    return {"jogo": {"id": 123, "casa": "Arsenal", "fora": "Chelsea",
                     "liga": "English Premier League",
                     "timestamp": START.timestamp()},
            "mercado": "Vitória Casa", "probabilidade": 0.69,
            "odd_minima": 1.52}


class IntegridadeOddsTests(unittest.TestCase):
    def test_hora_fixture_normal_aceite_e_sem_mutar_original(self):
        f = Fonte(START.isoformat())
        original = selecao()
        copia = copy.deepcopy(original)
        out = AuditoriaOdds(f).enriquecer([original])[0]
        self.assertEqual(original, copia)
        self.assertEqual(out.get("odd_real"), 1.85)
        self.assertEqual(f.odds_calls, 1)

    def test_hora_errada_bloqueada_antes_do_lote_e_preco(self):
        for desvio in (60, -60, 120, -120):
            with self.subTest(minutos=desvio):
                hora = (START + timedelta(minutes=desvio)).isoformat()
                f = Fonte(hora)
                out = AuditoriaOdds(f).enriquecer([selecao()])[0]
                self.assertEqual(out["_odds_diag"], "horario_fixture_incompativel")
                self.assertIn("horario_divergente", out["_odds_alertas"])
                self.assertNotIn("odd_real", out)
                self.assertEqual(f.lote_calls, 0)
                self.assertEqual(f.odds_calls, 0)

    def test_hora_desvio_ate_30_min_e_hora_ausente(self):
        f = Fonte((START + timedelta(minutes=25)).isoformat())
        self.assertIn("odd_real", AuditoriaOdds(f).enriquecer([selecao()])[0])
        for valor in (None, "", "2030-10-24T15:00:00"):
            f = Fonte(valor)
            out = AuditoriaOdds(f).enriquecer([selecao()])[0]
            self.assertEqual(out["_odds_diag"], "horario_fixture_nao_comprovado")
            self.assertEqual(f.odds_calls, 0)
            self.assertNotIn("odd_real", out)

    def test_modelo_sem_hora_nao_pode_ligar_odds_papi(self):
        f = Fonte(START.isoformat())
        s = selecao()
        s["jogo"].pop("timestamp")
        out = AuditoriaOdds(f).enriquecer([s])[0]
        self.assertEqual(out["_odds_diag"], "horario_fixture_nao_comprovado")
        self.assertEqual(f.odds_calls, 0)

    def test_guarda_categoria_juvenil_feminina_b_e_equipa_principal(self):
        casos = ("Arsenal U19", "Arsenal B", "Arsenal II", "Arsenal Women", "Arsenal Sub-21")
        for nome in casos:
            with self.subTest(nome=nome):
                self.assertTrue(equipas_categoria_incompativel("Arsenal", nome))
                self.assertEqual(
                    AuditoriaOdds._candidatos_evento(
                        [{"id": "juvenil", "casa": nome, "fora": "Chelsea"}],
                        "Arsenal", "Chelsea",
                    ), []
                )
        self.assertTrue(AuditoriaOdds._nome_equipa_compativel("AFC Arsenal", "Arsenal"))
        self.assertTrue(AuditoriaOdds._nome_equipa_compativel("Arsenal U19", "Arsenal U19"))
        self.assertFalse(AuditoriaOdds._nome_equipa_compativel("Arsenal U19", "Arsenal U21"))

    def test_quote_antigo_ou_sem_hora_so_alerta_sem_escrever_original(self):
        f = Fonte(START.isoformat(), odd_atualizada="2020-01-01T00:00:00Z")
        original = selecao()
        original_copy = copy.deepcopy(original)
        out = AuditoriaOdds(f).enriquecer([original])[0]
        self.assertEqual(original, original_copy)
        self.assertEqual(out["odd_real"], 1.85)
        self.assertIn("odd_desatualizada", out["_odds_alertas"])
        self.assertEqual(f.odds_calls, 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "auditoria.json"
            auditoria = VerificacaoOdds(path)
            self.assertEqual(auditoria.registar([out]), 1)
            self.assertIn("odd desatualizada",
                          auditoria.relatorio(SimpleNamespace(dados={"previsoes": []}),
                                              agora=START + timedelta(hours=2)))

    def test_frescura_relogio_sem_rede(self):
        referencia = datetime(2030, 10, 24, 14, tzinfo=timezone.utc)
        self.assertIsNone(classificar_frescura("2030-10-24T13:00:00Z", referencia))
        self.assertEqual(classificar_frescura("2030-10-24T07:59:00Z", referencia),
                         "odd_desatualizada")
        self.assertEqual(classificar_frescura("", referencia), "odd_sem_data_atualizacao")
        self.assertEqual(classificar_frescura("2030-10-24T14:06:00Z", referencia),
                         "odd_data_futura")
        self.assertEqual(verificar_hora_fixture(START.timestamp(), START.isoformat(),
                                               exigir_hora=True), (True, ""))


if __name__ == "__main__":
    unittest.main()
