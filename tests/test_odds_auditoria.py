import unittest

from odds_auditoria import AuditoriaOdds


class FonteFake:
    configurada = True
    nome_fonte = "Fonte Teste"

    def eventos_hoje(self):
        return [
            {"id": "evt1", "casa": "Atlético Madrid", "fora": "Osasuna"},
            {"id": "evt2", "casa": "AIK", "fora": "Mjällby AIF"},
        ]

    def odds_evento(self, event_id):
        if event_id == "evt1":
            return {
                "casa": "Atletico Madrid",
                "fora": "Osasuna",
                "fonte": "Fonte Teste",
                "mercados": [
                    {
                        "name": "Total Goals Over/Under",
                        "updatedAt": "2026-09-16T10:00:00Z",
                        "odds": [
                            {"seleção": "Under 3.5", "odd": 1.72},
                            {"seleção": "Over 3.5", "odd": 2.05},
                        ],
                    }
                ],
            }
        if event_id == "evt2":
            return {
                "casa": "AIK",
                "fora": "Mjallby AIF",
                "fonte": "Fonte Teste",
                "mercados": [
                    {
                        "name": "Total Goals",
                        "updatedAt": "2026-09-16T10:00:00Z",
                        "odds": [
                            {"seleção": "Over 2.5", "odd": 1.80},
                            {"seleção": "Under 2.5", "odd": 2.00},
                        ],
                    }
                ],
            }
        return None


class FonteDesligada:
    configurada = False


class OddsAuditoriaTests(unittest.TestCase):
    def test_enriquece_sem_alterar_ordem_ou_selecao(self):
        originais = [
            {
                "jogo": {"id": 1, "casa": "AIK", "fora": "Mjällby AIF"},
                "mercado": "Over 2.5 Golos",
                "probabilidade": 0.634,
            },
            {
                "jogo": {"id": 2, "casa": "Atlético Madrid", "fora": "Osasuna"},
                "mercado": "Under 3.5 Golos",
                "probabilidade": 0.644,
            },
        ]
        saida = AuditoriaOdds(FonteFake()).enriquecer(originais)

        self.assertEqual([x["mercado"] for x in saida], [x["mercado"] for x in originais])
        self.assertNotIn("odd_real", originais[0])
        self.assertEqual(saida[0]["odd_real"], 1.80)
        self.assertAlmostEqual(saida[0]["ev_real"], (0.634 * 1.80) - 1, places=6)
        self.assertEqual(saida[1]["odd_real"], 1.72)
        self.assertEqual(saida[1]["odds_fonte"], "Fonte Teste")

    def test_sem_fonte_nao_inventa_odds(self):
        selecoes = [
            {
                "jogo": {"id": 1, "casa": "Casa", "fora": "Fora"},
                "mercado": "Vitória Casa",
                "probabilidade": 0.60,
            }
        ]
        saida = AuditoriaOdds(FonteDesligada()).enriquecer(selecoes)
        self.assertEqual(len(saida), 1)
        self.assertNotIn("odd_real", saida[0])

    def test_correspondencia_ambigua_nao_guarda_odd(self):
        class FonteAmbigua(FonteFake):
            def eventos_hoje(self):
                return [
                    {"id": "a", "casa": "AIK", "fora": "Mjällby AIF"},
                    {"id": "b", "casa": "AIK", "fora": "Mjallby AIF"},
                ]

        selecoes = [
            {
                "jogo": {"id": 1, "casa": "AIK", "fora": "Mjällby AIF"},
                "mercado": "Over 2.5 Golos",
                "probabilidade": 0.63,
            }
        ]
        saida = AuditoriaOdds(FonteAmbigua()).enriquecer(selecoes)
        self.assertNotIn("odd_real", saida[0])


if __name__ == "__main__":
    unittest.main()
