import unittest
from proposta_linhas_seguras_shadow import validar_linha_totais

class LinhasSeguras(unittest.TestCase):
    def test_linha_correta(self):
        self.assertTrue(validar_linha_totais('Under 2.5 Golos', {'handicap':2.5,'name':'Total Goals'}, {'seleção':'Under','ref':'207'})[0])
    def test_substring_12_5(self):
        self.assertFalse(validar_linha_totais('Under 2.5 Golos', {'name':'Total Goals'}, {'seleção':'Under 12.5'})[0])
    def test_handicap_contraditorio(self):
        self.assertFalse(validar_linha_totais('Under 2.5 Golos', {'name':'Total Goals','handicap':2.5}, {'seleção':'Under 12.5'})[0])
    def test_linha_sem_prova(self):
        self.assertFalse(validar_linha_totais('Under 2.5 Golos', {'name':'Total Goals'}, {'seleção':'Under'})[0])
    def test_ref_id_numerico_nao_e_linha(self):
        self.assertTrue(validar_linha_totais('Under 2.5 Golos', {'name':'Total Goals','handicap':2.5}, {'seleção':'Under','ref':'123456'})[0])
    def test_linha_3_5_valida(self):
        self.assertTrue(validar_linha_totais('Under 3.5 Golos', {'name':'Total Goals','handicap':3.5}, {'seleção':'Under','ref':'207'})[0])
    def test_lado_errado(self):
        self.assertFalse(validar_linha_totais('Under 2.5 Golos', {'name':'Total Goals','handicap':2.5}, {'seleção':'Over'})[0])

if __name__=='__main__':
    unittest.main()
