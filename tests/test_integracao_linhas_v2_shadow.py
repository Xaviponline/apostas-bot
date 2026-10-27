"""Regressão offline: parser oficial vs validador V2, sem consultas externas."""
import unittest
from odds_auditoria import AuditoriaOdds
from validacao_linhas_v2_shadow import validar_linha_totais

class ComparacaoIntegracao(unittest.TestCase):
    @staticmethod
    def _item(line, name='Over Under Full Time', handicap=None, ref='207'):
        market={'name':name,'period':'fulltime'}
        if handicap is not None:market['handicap']=handicap
        return market,{'seleção':line,'ref':ref,'odd':1.8}
    def test_01_under_2_5_correto_preservado(self):
        m,s=self._item('Under',handicap=2.5)
        self.assertTrue(AuditoriaOdds._item_compativel('Under 2.5 Golos',m,s,'Casa','Fora'))
        self.assertTrue(validar_linha_totais('Under 2.5 Golos',m,s)[0])
    def test_02_under_3_5_correto_preservado(self):
        m,s=self._item('Under',handicap=3.5)
        self.assertTrue(AuditoriaOdds._item_compativel('Under 3.5 Golos',m,s,'Casa','Fora'))
        self.assertTrue(validar_linha_totais('Under 3.5 Golos',m,s)[0])
    def test_03_linha_12_5_textual_sem_handicap(self):
        m,s=self._item('Under 12.5',name='Total Goals')
        self.assertTrue(AuditoriaOdds._item_compativel('Under 2.5 Golos',m,s,'Casa','Fora'))
        self.assertFalse(validar_linha_totais('Under 2.5 Golos',m,s)[0])
    def test_04_handicap_2_5_com_selecao_12_5(self):
        m,s=self._item('Under 12.5',handicap=2.5)
        self.assertTrue(AuditoriaOdds._item_compativel('Under 2.5 Golos',m,s,'Casa','Fora'))
        self.assertFalse(validar_linha_totais('Under 2.5 Golos',m,s)[0])
    def test_05_ano_2026_nao_e_linha(self):
        m,s=self._item('Under',name='Total Goals 2026',handicap=2.5)
        self.assertTrue(validar_linha_totais('Under 2.5 Golos',m,s)[0])
    def test_06_sem_linha_nao_inventar(self):
        m,s=self._item('Under',name='Total Goals')
        self.assertFalse(validar_linha_totais('Under 2.5 Golos',m,s)[0])
    def test_07_periodo_e_guardas_permanecem_no_parser(self):
        m,s=self._item('Under',handicap=2.5)
        m['period']='firsthalf'
        self.assertFalse(AuditoriaOdds._mercado_compativel('Under 2.5 Golos',m))
        self.assertTrue(validar_linha_totais('Under 2.5 Golos',m,s)[0])

if __name__=='__main__':unittest.main()
