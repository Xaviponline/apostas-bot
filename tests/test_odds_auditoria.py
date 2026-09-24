import unittest

from odds_auditoria import AuditoriaOdds


class FonteFake:
    configurada = True
    nome_fonte = "Fonte Teste"

    def eventos_hoje(self):
        return [
            {"id": "evt1", "casa": "Atlético Madrid", "fora": "CA Osasuna"},
            {"id": "evt2", "casa": "AIK", "fora": "Mjällby AIF"},
        ]

    def odds_evento(self, event_id):
        if event_id == "evt1":
            return {
                "casa": "Atletico Madrid",
                "fora": "CA Osasuna",
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


class FonteLote:
    configurada = True
    nome_fonte = "Fonte Lote"

    def __init__(self):
        self.chamadas_lote = 0
        self.chamadas_individuais = 0

    def eventos_hoje(self):
        return [
            {
                "id": "evt1",
                "casa": "Portugal",
                "fora": "Wales",
                "tournament_id": 77,
            },
            {
                "id": "evt2",
                "casa": "Netherlands",
                "fora": "Germany",
                "tournament_id": 77,
            },
        ]

    def odds_eventos_em_lote(self, eventos):
        self.chamadas_lote += 1
        self.eventos_recebidos = [e["id"] for e in eventos]
        return {
            "evt1": {
                "id": "evt1",
                "fonte": self.nome_fonte,
                "mercados": [
                    {
                        "name": "Full Time Result",
                        "period": "fulltime",
                        "odds": [{"seleção": "1", "odd": 1.70}],
                    }
                ],
            },
            "evt2": {
                "id": "evt2",
                "fonte": self.nome_fonte,
                "mercados": [
                    {
                        "name": "Full Time Result",
                        "period": "fulltime",
                        "odds": [{"seleção": "1", "odd": 1.80}],
                    }
                ],
            },
        }

    def odds_evento(self, event_id):
        self.chamadas_individuais += 1
        raise AssertionError("Não devia consultar odds individualmente")




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


    def test_consulta_em_lote_evita_um_pedido_por_jogo(self):
        fonte = FonteLote()
        selecoes = [
            {
                "jogo": {"id": 1, "casa": "Portugal", "fora": "Wales"},
                "mercado": "Vitória Casa",
                "probabilidade": 0.66,
            },
            {
                "jogo": {"id": 2, "casa": "Netherlands", "fora": "Germany"},
                "mercado": "Vitória Casa",
                "probabilidade": 0.67,
            },
        ]

        saida = AuditoriaOdds(fonte).enriquecer(selecoes)

        self.assertEqual(fonte.chamadas_lote, 1)
        self.assertEqual(fonte.chamadas_individuais, 0)
        self.assertEqual(saida[0]["odd_real"], 1.70)
        self.assertEqual(saida[1]["odd_real"], 1.80)

    def test_normaliza_siglas_de_clube_sem_fuzzy_matching(self):
        self.assertEqual(
            AuditoriaOdds._chave_jogo("Atlético Madrid", "Osasuna"),
            AuditoriaOdds._chave_jogo("Atletico Madrid", "CA Osasuna"),
        )
        self.assertEqual(AuditoriaOdds._normalizar("AC Milan"), "milan")
        self.assertNotEqual(AuditoriaOdds._normalizar("Inter Milan"), "milan")

    def test_fallback_controlado_para_extensoes_de_nome(self):
        eventos = [
            {"id": "a", "casa": "AIK Solna", "fora": "Mjällby AIF"},
            {"id": "b", "casa": "Deportivo La Coruna", "fora": "Sevilla"},
            {"id": "c", "casa": "Levante UD", "fora": "Athletic Bilbao"},
        ]
        self.assertEqual(
            AuditoriaOdds._candidatos_evento(eventos, "AIK", "Mjällby AIF")[0]["id"],
            "a",
        )
        self.assertEqual(
            AuditoriaOdds._candidatos_evento(eventos, "Deportivo", "Sevilla")[0]["id"],
            "b",
        )
        self.assertEqual(
            AuditoriaOdds._candidatos_evento(eventos, "Levante", "Athletic Club")[0]["id"],
            "c",
        )

    def test_fallback_ambiguo_continua_bloqueado(self):
        eventos = [
            {"id": "a", "casa": "Deportivo La Coruna", "fora": "Sevilla"},
            {"id": "b", "casa": "Deportivo B", "fora": "Sevilla"},
        ]
        candidatos = AuditoriaOdds._candidatos_evento(eventos, "Deportivo", "Sevilla")
        self.assertEqual(len(candidatos), 2)

    def test_diagnostica_evento_nao_encontrado(self):
        selecoes = [
            {
                "jogo": {"id": 9, "casa": "Equipa X", "fora": "Equipa Y"},
                "mercado": "Over 2.5 Golos",
                "probabilidade": 0.60,
            }
        ]
        saida = AuditoriaOdds(FonteFake()).enriquecer(selecoes)
        self.assertEqual(saida[0]["_odds_diag"], "evento_nao_encontrado")
        self.assertNotIn("odd_real", saida[0])

    def test_diagnostica_linha_ou_selecao_nao_disponivel(self):
        selecoes = [
            {
                "jogo": {"id": 1, "casa": "AIK", "fora": "Mjällby AIF"},
                "mercado": "Over 3.5 Golos",
                "probabilidade": 0.60,
            }
        ]
        saida = AuditoriaOdds(FonteFake()).enriquecer(selecoes)
        self.assertEqual(saida[0]["_odds_diag"], "linha_ou_selecao_nao_disponivel")
        self.assertNotIn("odd_real", saida[0])

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
        self.assertEqual(saida[0]["_odds_diag"], "evento_ambiguo")


if __name__ == "__main__":
    unittest.main()
