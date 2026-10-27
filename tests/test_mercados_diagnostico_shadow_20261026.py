import unittest
from mercados_diagnostico_shadow import test_item, diagnose_payload, numeric_lines


def sample(line=2.5,sel='Under',name='Over Under Full Time',period='fulltime'):
    market={'name':name,'period':period,'handicap':line}
    item={'seleção':sel, 'odd':1.83,'ref':'9983712992'}
    return market,item

class ShadowTests(unittest.TestCase):
    def assertMatches(self,target,market,item,expected):
        accepted,_=test_item(target,market,item)
        self.assertEqual(accepted,expected)
    def test_01_base(self):
        m,s=sample();self.assertMatches('Under 2.5 Golos',m,s,True)
    def test_02_linha_diferente(self):
        m,s=sample(3.5);self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_03_texto_12_5_nao_2_5(self):
        m,s=sample(None,'Under 12.5',name='Total Goals');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_04_nome_12_5_nao_2_5(self):
        m,s=sample(None,'Under',name='Total Goals 12.5');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_05_handicap_contradicao(self):
        m,s=sample(2.5,'Under 3.5');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_06_nome_contradicao(self):
        m,s=sample(2.5,'Under',name='Total Goals 3.5');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_07_periodo_primeira_parte(self):
        m,s=sample(period='firsthalf');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_08_periodo_vazio(self):
        m,s=sample(period='');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_09_mercado_cantos(self):
        m,s=sample(name='Corners Over Under Full Time');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_10_total_equipa(self):
        m,s=sample(name='Over Under Team 1');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_11_ref_id_nao_virar_linha(self):
        m,s=sample(None,'Under 2.5',name='Total Goals');self.assertMatches('Under 2.5 Golos',m,s,True)
    def test_12_selo_lado(self):
        m,s=sample(sel='Over');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_13_btts_sim(self):
        m,s=sample(None,'Yes','Both Teams To Score');self.assertMatches('Ambas Marcam',m,s,True)
    def test_14_resultado_casa(self):
        m,s=sample(None,'1','Full Time Result');self.assertMatches('Vitória Casa',m,s,True)
    def test_15_ambiguidade_duas_cotacoes(self):
        m,s=sample();d=diagnose_payload({'mercados':[{**m,'odds':[s,s]}]},'Under 2.5 Golos')
        self.assertEqual(d['estado'],'associacao_ambigua')
    def test_16_sem_linha_rejeita(self):
        m,s=sample(None,'Under','Total Goals');self.assertMatches('Under 2.5 Golos',m,s,False)
    def test_17_numeros_exatos(self):
        self.assertEqual(numeric_lines('Under 12.5'),{12.5})
    def test_18_periodo_e_outcome_id_nao_afetam(self):
        m,s=sample(None,'Under 2.5',name='Total Goals');s['ref']='123456789';self.assertMatches('Under 2.5 Golos',m,s,True)

if __name__=='__main__':unittest.main()
