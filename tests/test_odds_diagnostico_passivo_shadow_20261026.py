import unittest
from odds_diagnostico_passivo_shadow import diagnosticar_payload

CAP='2026-10-26T15:00:00Z'
KICK='2026-10-26T19:00:00Z'

def payload(nome='Total Goals',handicap=2.5,sel='Under',price=1.8,**kwargs):
    market={'name':nome,'period':'fulltime','handicap':handicap,'odds':[{'seleção':sel,'odd':price,'changedAt':'2026-10-26T14:45:00Z'}]}
    market.update(kwargs)
    return {'bookmaker_disponivel':True,'mercados':[market]}

class ShadowDiagnosticoTests(unittest.TestCase):
    def run_case(self,p,mercado='Under 2.5 Golos',capture=CAP,kick=KICK):
        return diagnosticar_payload(p,mercado,capture,kick)
    def test_cotacao_observada_nao_equivale_a_execucao(self):
        d=self.run_case(payload());self.assertEqual(d['estado'],'uma_cotacao_observada_sem_prova_de_execucao')
        self.assertEqual(d['contagens']['ultima_alteracao_recente_nao_prova_disponibilidade'],1)
    def test_linha_12_5_nao_2_5(self):
        self.assertEqual(self.run_case(payload(nome='Total Goals 12.5',handicap=None))['precos_validos_observados'],0)
    def test_handicap_divergente(self):
        self.assertEqual(self.run_case(payload(handicap=12.5))['precos_validos_observados'],0)
    def test_handicap_contradito(self):
        self.assertEqual(self.run_case(payload(sel='Under 12.5'))['precos_validos_observados'],0)
    def test_sem_periodo(self):
        self.assertEqual(self.run_case(payload(period=''))['precos_validos_observados'],0)
    def test_sem_preco(self):
        d=self.run_case(payload(price=None));self.assertEqual(d['estado'],'estrutura_compativel_mas_sem_preco_valido')
    def test_preco_infinito(self):
        self.assertEqual(self.run_case(payload(price=float('inf')))['precos_validos_observados'],0)
    def test_preco_bool(self):
        self.assertEqual(self.run_case(payload(price=True))['precos_validos_observados'],0)
    def test_mercado_inativo(self):
        self.assertEqual(self.run_case(payload(marketActive=False))['precos_validos_observados'],0)
    def test_bookmaker_inativo(self):
        self.assertEqual(self.run_case({'bookmaker_disponivel':False,'mercados':[]})['estado'],'bookmaker_explicitamente_inativo')
    def test_antiga_nao_bloqueada_retroativamente(self):
        d=payload();d['mercados'][0]['odds'][0]['changedAt']='2026-10-24T01:00:00Z'
        r=self.run_case(d);self.assertEqual(r['precos_validos_observados'],1)
        self.assertEqual(r['contagens']['ultima_alteracao_ha_mais_6h'],1)
    def test_alteracao_futura_sinalizada(self):
        d=payload();d['mercados'][0]['odds'][0]['changedAt']='2026-10-26T17:00:00Z'
        self.assertEqual(self.run_case(d)['contagens']['ultima_alteracao_futura'],1)
    def test_hora_nao_comprovada(self):
        d=self.run_case(payload(),capture='2026-10-26T15:00:00')
        self.assertEqual(d['contagens']['captura_sem_hora_comprovada'],1)
    def test_pos_inicio(self):
        self.assertEqual(self.run_case(payload(),capture='2026-10-26T20:00:00Z')['contagens']['captura_pos_kickoff'],1)
    def test_duplicados_ambiguos(self):
        d=payload();d['mercados'][0]['odds'].append(dict(d['mercados'][0]['odds'][0]))
        self.assertEqual(self.run_case(d)['estado'],'multiplas_cotacoes_estruturalmente_compativeis')
    def test_sem_lista_de_mercados(self):
        self.assertEqual(self.run_case({'mercados':{}})['estado'],'lista_mercados_ausente_ou_excessiva')
    def test_nao_expoe_precos_nem_ids(self):
        d=payload();d['mercados'][0]['odds'][0]['ref']='123456789'
        resultado=self.run_case(d)
        self.assertNotIn('123456789',repr(resultado));self.assertNotIn('1.8',repr(resultado))

if __name__=='__main__':unittest.main()
