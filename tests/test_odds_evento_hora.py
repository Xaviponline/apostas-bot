import unittest
from datetime import datetime, timezone

from odds_auditoria import AuditoriaOdds


class FonteFixturesDuplicados:
    configurada = True
    nome_fonte = "Fonte Teste"

    def eventos_hoje(self):
        return [
            {
                "id": "certo",
                "casa": "Real Betis",
                "fora": "Getafe",
                "data": "2026-09-17T17:00:00Z",
            },
            {
                "id": "outro",
                "casa": "Real Betis",
                "fora": "Getafe",
                "data": "2026-09-17T21:00:00Z",
            },
        ]

    def odds_evento(self, event_id):
        odd = 1.80 if event_id == "certo" else 2.40
        return {
            "id": event_id,
            "casa": "Real Betis",
            "fora": "Getafe",
            "fonte": self.nome_fonte,
            "bookmaker_disponivel": True,
            "mercados": [
                {
                    "name": "Total Goals",
                    "odds": [
                        {"seleção": "Under 2.5", "odd": odd},
                        {"seleção": "Over 2.5", "odd": 2.00},
                    ],
                }
            ],
        }


class OddsEventoHoraTests(unittest.TestCase):
    def test_mesmas_equipas_desempatam_pela_hora(self):
        ts = datetime(2026, 9, 17, 17, 0, tzinfo=timezone.utc).timestamp()
        selecoes = [
            {
                "jogo": {
                    "id": 1,
                    "casa": "Real Betis",
                    "fora": "Getafe",
                    "timestamp": ts,
                },
                "mercado": "Under 2.5 Golos",
                "probabilidade": 0.636,
            }
        ]
        saida = AuditoriaOdds(FonteFixturesDuplicados()).enriquecer(selecoes)
        self.assertEqual(saida[0]["odd_real"], 1.80)
        self.assertEqual(saida[0]["odds_event_id"], "certo")

    def test_mesma_hora_continua_ambigua(self):
        ts = datetime(2026, 9, 17, 17, 0, tzinfo=timezone.utc).timestamp()
        eventos = [
            {"id": "a", "data": "2026-09-17T17:00:00Z"},
            {"id": "b", "data": "2026-09-17T17:00:00Z"},
        ]
        self.assertEqual(
            len(AuditoriaOdds._desempatar_evento_por_hora(eventos, ts)),
            2,
        )

    def test_ferencvarosi_e_ferencvaros_sao_equivalentes_controlados(self):
        self.assertTrue(
            AuditoriaOdds._nome_equipa_compativel(
                "Ferencvaros", "Ferencvárosi TC"
            )
        )


if __name__ == "__main__":
    unittest.main()
