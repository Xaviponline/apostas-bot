import unittest
from validacao_linhas_v2_shadow import validar_linha_totais as check

def market(handicap=None, name='Over Under Full Time'):
    m={'name':name, 'period':'fulltime'}
    if handicap is not None:m['handicap']=handicap
    return m

class Tests(unittest.TestCase):
    def ok(self, target, m, sel, ref='207'):
        self.assertTrue(check(target,m,{'seleção':sel,'ref':ref})[0], (target,m,sel,ref))
    def no(self, target, m, sel, ref='207'):
        self.assertFalse(check(target,m,{'seleção':sel,'ref':ref})[0], (target,m,sel,ref))
    def test_01_base(self):self.ok('Under 2.5 Golos',market(2.5),'Under')
    def test_02_3_5(self):self.ok('Under 3.5 Golos',market(3.5),'Under')
    def test_03_12_5_no_handicap(self):self.no('Under 2.5 Golos',market(),'Under 12.5')
    def test_04_12_5_with_handicap(self):self.no('Under 2.5 Golos',market(2.5),'Under 12.5')
    def test_05_name_12_5(self):self.no('Under 2.5 Golos',market(name='Total Goals 12.5'),'Under')
    def test_06_name_2026(self):self.ok('Under 2.5 Golos',market(2.5,'Total Goals 2026'),'Under')
    def test_07_ref_numeric(self):self.ok('Under 2.5 Golos',market(2.5),'Under','9983712992')
    def test_08_ref_explicit(self):self.ok('Under 2.5 Golos',market(),'Under','2.5/under')
    def test_09_ref_wrong(self):self.no('Under 2.5 Golos',market(),'Under','12.5/under')
    def test_10_no_line(self):self.no('Under 2.5 Golos',market(),'Under')
    def test_11_wrong_side(self):self.no('Under 2.5 Golos',market(2.5),'Over')
    def test_12_handicap_wrong(self):self.no('Under 2.5 Golos',market(3.5),'Under')
    def test_13_handicap_bool(self):self.no('Under 2.5 Golos',market(True),'Under')
    def test_14_handicap_nan(self):self.no('Under 2.5 Golos',market(float('nan')),'Under')
    def test_15_decimal_comma(self):self.ok('Under 2.5 Golos',market(),'Under 2,5')
    def test_16_explicit_integer(self):self.ok('Under 2 Golos',market(name='Total Goals line 2'),'Under')
    def test_17_ambiguous(self):self.no('Under 2.5 Golos',market(),'Under 2.5 / 3.5')
    def test_18_year_no_proof(self):self.no('Under 2.5 Golos',market(name='Total Goals 2026'),'Under')
    def test_19_no_data(self):self.no('Under 2.5 Golos',{},'Under')
    def test_20_half_no_change(self):self.ok('Over 1.5 Golos',market(1.5),'Over')
    def test_21_other_market(self):self.no('Ambas Marcam',market(2.5),'Under')
    def test_22_ref_numeric_small(self):self.ok('Under 2.5 Golos',market(2.5),'Under','2')
    def test_23_ref_line_with_other_side(self):self.no('Under 2.5 Golos',market(),'Under','12.5/over')
    def test_24_name_decimals_with_year(self):self.ok('Under 2.5 Golos',market(2.5,'Total Goals 2.5 Season 2026'),'Under')

    def test_25_lado_over_contra_ref_under(self):self.no('Under 2.5 Golos',market(2.5),'Over','2.5/under')
    def test_26_lado_under_contra_ref_over(self):self.no('Under 2.5 Golos',market(2.5),'Under','2.5/over')
    def test_27_selecao_ambigua(self):self.no('Under 2.5 Golos',market(2.5),'Over Under')
    def test_28_lado_apenas_na_ref(self):self.ok('Under 2.5 Golos',market(2.5),'','2.5/under')

if __name__=='__main__':unittest.main(verbosity=2)
