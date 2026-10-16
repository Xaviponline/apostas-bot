"""Observabilidade sem chamadas adicionais nem mudanças no output do modelo."""
import copy
import unittest
from datetime import datetime, timezone

from odds_auditoria import AuditoriaOdds


def timestamp_utc(hora):
    return datetime(2099, 10, 15, hora, 45, tzinfo=timezone.utc).timestamp()


def selecao(casa, fora, hora=17):
    return {
        "jogo": {
            "casa": casa, "fora": fora, "timestamp": timestamp_utc(hora),
            "liga": "Competição",
        },
        "mercado": "Vitória Casa",
        "probabilidade": 0.65,
        "odd_minima": 1.61,
        "ranking_modelo": 2,
    }


class FonteTelemetriaFake:
    configurada = True
    nome_fonte = "OddsPapi fake"

    def __init__(self):
        self.consultas_complementares = 0
        self.consultas_odds = []

    def eventos_hoje(self):
        return [{
            "id": "principal", "casa": "Portugal", "fora": "Wales",
            "data": "2099-10-15T17:45:00Z",
        }]

    def eventos_complementares(self):
        self.consultas_complementares += 1
        return [{
            "id": "extra", "casa": "Hearts", "fora": "Nordsjaelland",
            "data": "2099-10-15T17:45:00Z",
        }]

    def odds_evento(self, event_id):
        self.consultas_odds.append(event_id)
        if event_id not in {"principal", "extra"}:
            return None
        return {
            "id": event_id,
            "mercados": [{
                "name": "Full Time Result",
                "period": "fulltime",
                "odds": [{"seleção": "1", "odd": 1.81}],
            }],
            "fonte": self.nome_fonte,
        }


class TelemetriaOddsTests(unittest.TestCase):
    def test_contabiliza_mesma_ronda_principal_e_complementar_sem_mudar_snapshots(self):
        fonte = FonteTelemetriaFake()
        entrada = [
            selecao("Portugal", "Wales"),
            selecao("Heart of Midlothian", "Nordsjælland"),
            selecao("A", "B"),
        ]
        antes = copy.deepcopy(entrada)
        with self.assertLogs(level="INFO") as logs:
            resultado = AuditoriaOdds(fonte).enriquecer(
                entrada, fallback_individual_ausentes=True,
            )
        linha = next(x for x in logs.output if "ODDS_COBERTURA |" in x)
        self.assertIn("modo=recuperacao", linha)
        self.assertIn("selecoes=3", linha)
        self.assertIn("fixtures_primarios=1", linha)
        self.assertIn("fixtures_complementares=1", linha)
        self.assertIn("odds_primarias=1", linha)
        self.assertIn("odds_complementares=1", linha)
        self.assertIn("sem_fixture_validado=1", linha)
        self.assertIn("sem_cotacao=1", linha)
        self.assertEqual([x.get("odd_real") for x in resultado], [1.81, 1.81, None])
        self.assertEqual(entrada, antes)
        self.assertEqual(fonte.consultas_complementares, 1)
        self.assertEqual(set(fonte.consultas_odds), {"principal", "extra"})

    def test_modo_normal_nunca_pede_descoberta_complementar(self):
        fonte = FonteTelemetriaFake()
        with self.assertLogs(level="INFO") as logs:
            resultado = AuditoriaOdds(fonte).enriquecer([
                selecao("Portugal", "Wales"),
                selecao("Hearts", "Nordsjaelland"),
            ])
        linha = next(x for x in logs.output if "ODDS_COBERTURA |" in x)
        self.assertIn("modo=normal", linha)
        self.assertIn("fixtures_complementares=0", linha)
        self.assertIn("odds_complementares=0", linha)
        self.assertEqual(fonte.consultas_complementares, 0)
        self.assertEqual(resultado[1]["_odds_diag"], "evento_nao_encontrado")

    def test_odd_pre_existente_nao_conta_como_nova_cotacao(self):
        fonte = FonteTelemetriaFake()
        entrada = selecao("Sem", "Jogo")
        entrada["odd_real"] = 3.50  # não foi recuperada nesta ronda
        with self.assertLogs(level="INFO") as logs:
            resultado = AuditoriaOdds(fonte).enriquecer([entrada])
        linha = next(x for x in logs.output if "ODDS_COBERTURA |" in x)
        self.assertIn("odds_primarias=0", linha)
        self.assertIn("odds_complementares=0", linha)
        self.assertIn("sem_cotacao=1", linha)
        self.assertEqual(resultado[0]["odd_real"], 3.50)

    def test_hora_invalida_nao_conta_fixture_complementar(self):
        fonte = FonteTelemetriaFake()
        with self.assertLogs(level="INFO") as logs:
            resultado = AuditoriaOdds(fonte).enriquecer([
                selecao("Hearts", "Nordsjaelland", hora=20)
            ], fallback_individual_ausentes=True)
        linha = next(x for x in logs.output if "ODDS_COBERTURA |" in x)
        self.assertIn("fixtures_complementares=0", linha)
        self.assertIn("sem_fixture_validado=1", linha)
        self.assertEqual(resultado[0]["_odds_diag"], "horario_recuperacao_nao_validado")
        self.assertEqual(fonte.consultas_odds, [])


if __name__ == "__main__":
    unittest.main()
