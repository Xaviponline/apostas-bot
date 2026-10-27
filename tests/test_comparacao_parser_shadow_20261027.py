import unittest
from mercados_diagnostico_shadow import test_item

class DivergenciasParserShadow(unittest.TestCase):
    def test_linha_12_5_nao_pode_ser_2_5(self):
        m={'name':'Over Under Full Time','period':'fulltime'}
        s={'seleção':'Under 12.5','ref':'12.5/under'}
        self.assertEqual(test_item('Under 2.5 Golos',m,s)[0],False)

    def test_linha_correta_2_5(self):
        m={'name':'Over Under Full Time','period':'fulltime','handicap':2.5}
        s={'seleção':'Under','ref':'2.5/under'}
        self.assertEqual(test_item('Under 2.5 Golos',m,s)[0],True)

    def test_periodo_ausente_rejeitado(self):
        m={'name':'Over Under Full Time','handicap':2.5}
        s={'seleção':'Under','ref':'2.5/under'}
        self.assertEqual(test_item('Under 2.5 Golos',m,s)[1],'periodo_ausente_ou_incompativel')

    def test_handicap_contraditorio(self):
        m={'name':'Over Under Full Time','period':'fulltime','handicap':2.5}
        s={'seleção':'Under 12.5','ref':'12.5/under'}
        self.assertEqual(test_item('Under 2.5 Golos',m,s)[0],False)

if __name__=='__main__':unittest.main()
