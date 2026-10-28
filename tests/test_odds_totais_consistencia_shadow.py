"""Regressões offline de linhas incompatíveis; não consultar fornecedor nem alterar V1.3."""
import unittest

from odds_auditoria import AuditoriaOdds


def mercado(linha):
    return {
        "name": "Over Under Full Time", "period": "fulltime",
        "handicap": linha, "playerProp": False,
    }


def odd(lado, ref=""):
    return {"seleção": lado, "ref": ref, "odd": 1.86}


def associa(target, m, outcome):
    return AuditoriaOdds._item_compativel(target, m, outcome, "Celtic", "Dundee United")


class ValidacaoEstritaTotaisTests(unittest.TestCase):
    def test_nao_confundir_8_5_com_2_5(self):
        self.assertFalse(associa("Over 2.5 Golos", mercado(8.5), odd("Over", "8.5/over")))

    def test_nao_ignorar_referencia_contraditoria(self):
        self.assertFalse(associa("Over 2.5 Golos", mercado(2.5), odd("Over", "8.5/over")))

    def test_nao_confundir_12_5_com_2_5_por_substring(self):
        self.assertFalse(associa("Under 2.5 Golos",
                                {"name": "Total Goals", "period": "fulltime"},
                                odd("Under 12.5", "12.5/under")))

    def test_linha_sem_prova_rejeitada(self):
        self.assertFalse(associa("Over 2.5 Golos",
                                {"name": "Total Goals", "period": "fulltime"},
                                odd("Over", "207")))

    def test_linha_provada_pelo_handicap_aceite(self):
        self.assertTrue(associa("Over 2.5 Golos", mercado(2.5), odd("Over", "207")))
        self.assertTrue(associa("Under 3.5 Golos", mercado(3.5), odd("Under", "3.5/under")))

    def test_linha_provada_pela_referencia_sem_handicap(self):
        self.assertTrue(associa("Over 2.5 Golos",
                               {"name": "Total Goals", "period": "fulltime"},
                               odd("Over", "2.5/over")))

    def test_lado_contraditorio_rejeitado(self):
        self.assertFalse(associa("Under 2.5 Golos", mercado(2.5), odd("Under", "2.5/over")))

    def test_handicap_nao_numerico_rejeitado(self):
        self.assertFalse(associa("Over 2.5 Golos", mercado("invalid"), odd("Over", "2.5/over")))

    def test_dados_dos_restantes_mercados_nao_mudam(self):
        self.assertTrue(AuditoriaOdds._item_compativel(
            "Vitória Casa", {"name":"Full Time Result","period":"fulltime"},
            {"seleção":"1","odd":1.8}, "Casa", "Fora"
        ))


if __name__ == "__main__":
    unittest.main()
