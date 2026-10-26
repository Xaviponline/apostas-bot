import unittest
from scripts.diagnostico_payload_mercados_shadow import inspect


def data(selection, handicap=None, period='fulltime', name='Total Goals', ref=''):
    m = {'name': name, 'period': period,
         'odds': [{'seleção': selection, 'ref': ref, 'odd': 1.85}]}
    if handicap is not None: m['handicap'] = handicap
    return {'mercados': [m]}


class TestDiagnosticoPayload(unittest.TestCase):
    def test_valido(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under', 2.5))['estado'], 'um_candidato_shadow')

    def test_nao_confunde_12_5_e_2_5(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under 12.5'))['estado'], 'sem_correspondencia_segura')

    def test_nega_texto_contraditorio(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under 3.5', 2.5))['estado'], 'sem_correspondencia_segura')

    def test_periodo(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under', 2.5, 'firsthalf'))['estado'], 'sem_correspondencia_segura')

    def test_sem_periodo(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under', 2.5, ''))['estado'], 'sem_correspondencia_segura')

    def test_ignora_ref_id_numerico(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under', 2.5, ref='10592937780'))['estado'], 'um_candidato_shadow')

    def test_nao_aceita_cantos(self):
        self.assertEqual(inspect('Under 2.5 Golos', data('Under', 2.5, name='Corners Total Goals'))['estado'], 'sem_correspondencia_segura')

    def test_nunca_faz_associacao_ambigua(self):
        p = data('Under', 2.5)
        p['mercados'][0]['odds'].append({'seleção':'Under', 'odd':1.9})
        self.assertEqual(inspect('Under 2.5 Golos', p)['estado'], 'ambiguo_multiplos_candidatos')

    def test_nao_reporta_odd_nem_ids(self):
        a = inspect('Under 2.5 Golos', data('Under', 2.5, ref='10592937780'))
        self.assertNotIn('10592937780', repr(a))
        self.assertNotIn('1.85', repr(a))


if __name__ == '__main__':
    unittest.main()
