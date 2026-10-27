import copy
import unittest

from diagnostico_etapas_odds_shadow import (
    diagnosticar_etapas, resumir_rastreio_historico, verificar_evento,
)

T = '2026-10-26T15:00:00Z'
MODELO = {'casa':'Casa', 'fora':'Fora', 'timestamp_jogo':1793037600.0, 'mercado':'Under 2.5 Golos'}
# 2026-10-26 18:00 UTC
FIXTURE = {'id':'id123456789', 'casa':'Casa', 'fora':'Fora', 'data':'2026-10-26T18:00:00Z', 'liga':'Liga Portugal'}

def payload(line=2.5, text='Under', nome='Total Goals', period='fulltime', preco=1.8):
    return {'id':'id123456789','casa':'Casa','fora':'Fora','liga':'Portuguese Primeira Liga',
            'bookmaker_disponivel':True, 'mercados':[
                {'name':nome,'period':period,'handicap':line,
                 'odds':[{'seleção':text,'ref':'99557','odd':preco,'changedAt':'2026-10-26T14:00:00Z'}]}
            ]}

class FasesShadowTests(unittest.TestCase):
    def run_case(self,modelo=None,fixture=None,fonte=None,captura=T):
        return diagnosticar_etapas(modelo or MODELO,fixture or FIXTURE,fonte or payload(),captura)

    def test_evento_valido_e_preco_nao_executabilidade(self):
        v=self.run_case()
        self.assertEqual(v['evento'],'evento_identificado_com_hora_prejogo')
        self.assertEqual(v['resultado'],'um_preco_observado_nao_executabilidade')
        self.assertEqual(v['precos_observados'],1)
        self.assertEqual(v['etapa_a_investigar'],'execucao_nao_verificada')
    def test_liga_texto_diverso_e_so_alerta(self):
        self.assertIn('nome_competicao_por_confirmar',self.run_case()['avisos'])
    def test_identificacao_espera_id_fonte_iguais(self):
        f=dict(FIXTURE,id='id000')
        self.assertEqual(self.run_case(fixture=f)['evento'],'fixture_id_fonte_divergente')
    def test_id_fonte_falta(self):
        f=dict(FIXTURE,id='')
        self.assertEqual(self.run_case(fixture=f)['evento'],'fixture_id_fonte_nao_comprovado')
    def test_nomes_trocados_rejeitados(self):
        f=dict(FIXTURE,casa='Fora',fora='Casa')
        self.assertEqual(self.run_case(fixture=f)['evento'],'nome_equipa_nao_confirmado')
    def test_juvenil_vs_senior_rejeitado(self):
        f=dict(FIXTURE,casa='Casa U19')
        self.assertEqual(self.run_case(fixture=f)['evento'],'categoria_equipa_incompativel')
    def test_categoria_b_vs_senior_rejeitada(self):
        f=dict(FIXTURE,casa='Casa B')
        self.assertEqual(self.run_case(fixture=f)['evento'],'categoria_equipa_incompativel')
    def test_hora_mais_90min_rejeita(self):
        f=dict(FIXTURE,data='2026-10-26T20:00:01Z')
        self.assertEqual(self.run_case(fixture=f)['evento'],'hora_fixture_incompativel')
    def test_hora_ate_90min_admite(self):
        f=dict(FIXTURE,data='2026-10-26T19:30:00Z')
        self.assertEqual(self.run_case(fixture=f)['evento'],'evento_identificado_com_hora_prejogo')
    def test_captura_depois_do_kickoff(self):
        self.assertEqual(self.run_case(captura='2026-10-26T18:00:00Z')['evento'],'captura_pos_kickoff')
    def test_captura_sem_timezone(self):
        self.assertEqual(self.run_case(captura='2026-10-26T15:00:00')['evento'],'captura_sem_hora_comprovada')
    def test_12_5_outra_linha(self):
        d=self.run_case(fonte=payload(line=12.5,text='Under 12.5'))
        self.assertEqual(d['precos_observados'],0)
        self.assertEqual(d['fases']['linha'],1)
    def test_periodo_incompativel(self):
        d=self.run_case(fonte=payload(period='firsthalf'))
        self.assertEqual(d['etapa_a_investigar'],'periodo')
    def test_selecao_outro_lado(self):
        d=self.run_case(fonte=payload(text='Over'))
        self.assertEqual(d['etapa_a_investigar'],'selecao')
    def test_preco_ausente(self):
        d=self.run_case(fonte=payload(preco=None))
        self.assertEqual(d['etapa_a_investigar'],'preco')
    def test_bookmaker_inativo(self):
        p=payload();p['bookmaker_disponivel']=False
        self.assertEqual(self.run_case(fonte=p)['etapa_a_investigar'],'bookmaker')
    def test_catalogo_placeholder(self):
        d=self.run_case(fonte=payload(nome='Market 82918'))
        self.assertEqual(d['fases']['catalogo'],1)
    def test_sem_mercados_nao_inventa(self):
        p=payload();p['mercados']=[]
        self.assertEqual(self.run_case(fonte=p)['etapa_a_investigar'],'catalogo_ou_lista_vazia')
    def test_antiga_indica_necessidade_revisao(self):
        p=payload();p['mercados'][0]['odds'][0]['changedAt']='2026-10-23T01:00:00Z'
        d=self.run_case(fonte=p)
        self.assertEqual(d['precos_observados'],1)
        self.assertEqual(d['etapa_a_investigar'],'tempo')
    def test_multiplos_precos_nao_validam_preco(self):
        p=payload();p['mercados'][0]['odds'].append(dict(p['mercados'][0]['odds'][0]))
        self.assertEqual(self.run_case(fonte=p)['resultado'],'multiplos_precos_observados')
    def test_sem_identidade_nao_associa_preco(self):
        p=payload();p['id']='id987654321'
        d=self.run_case(fonte=p)
        self.assertEqual(d['resultado'],'evento_nao_comprovado')
    def test_nao_altera_dados_nem_expoe_valores(self):
        m=copy.deepcopy(MODELO);f=copy.deepcopy(FIXTURE);p=payload(preco=11.11)
        p0=copy.deepcopy(p)
        d=self.run_case(modelo=m,fixture=f,fonte=p)
        self.assertEqual(p,p0)
        self.assertNotIn('11.11',str(d));self.assertNotIn('id123456789',str(d))
        self.assertNotIn('Casa',str(d))
    def test_historico_nao_alega_causa_exata(self):
        r=resumir_rastreio_historico([
            {'diagnostico':'mercado_nao_disponivel'},
            {'diagnostico':'linha_ou_selecao_nao_disponivel'},
            {'diagnostico':'evento_nao_encontrado'},
            {'diagnostico':'fixture_omitido_no_lote'},
        ])
        self.assertEqual(r['mercado_ou_catalogo_indeterminado'],1)
        self.assertEqual(r['linha_ou_selecao_indeterminada'],1)
        self.assertEqual(r['evento'],1)
        self.assertEqual(r['lote'],1)

if __name__=='__main__':unittest.main()
