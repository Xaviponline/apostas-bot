"""Comparação offline usando a fixture OddsPapi já existente no projeto.

Não faz chamadas à API nem modifica a auditoria de produção.
"""
import unittest
from odds_auditoria import AuditoriaOdds
from validacao_linhas_v2_shadow import validar_linha_totais
from test_odds_linhas_papi import PapiLinhasSession
from odds_betano import OddsBetano


class ReplayFixtureOddsPapiShadow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = OddsBetano(
            papi_key="teste", provider="oddspapi", session=PapiLinhasSession()
        ).odds_evento("id100")

    def test_linhas_legitimas_preservadas(self):
        for alvo in ("Under 2.5 Golos", "Under 3.5 Golos", "Over 2.5 Golos"):
            with self.subTest(alvo=alvo):
                candidatos = []
                for mercado in self.dados["mercados"]:
                    if not AuditoriaOdds._mercado_compativel(alvo, mercado):
                        continue
                    for odd in mercado["odds"]:
                        antigo = AuditoriaOdds._item_compativel(
                            alvo, mercado, odd, "Casa", "Fora"
                        )
                        novo = validar_linha_totais(alvo, mercado, odd)[0]
                        self.assertEqual(novo, antigo)
                        if novo:
                            candidatos.append((mercado, odd))
                self.assertEqual(len(candidatos), 1)

    def test_nao_associar_linha_errada(self):
        for alvo in ("Under 1.5 Golos", "Over 1.5 Golos"):
            with self.subTest(alvo=alvo):
                self.assertFalse(any(
                    validar_linha_totais(alvo, m, odd)[0]
                    for m in self.dados["mercados"]
                    if AuditoriaOdds._mercado_compativel(alvo, m)
                    for odd in m["odds"]
                ))


if __name__ == "__main__":
    unittest.main()
