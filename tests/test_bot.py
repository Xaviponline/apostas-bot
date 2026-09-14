import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
from gestor_apostas import GestorApostas
from main_sofascore import BotPremiumReal
from rastreador_resultados import RastreadorResultados
from analisador_inteligente import AnalisadorInteligente
from buscador_jogos_reais import BuscadorJogosReais
from previsoes_premium import RegistoPrevisoes

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'apostas_historico.json'
        self.g = GestorApostas(self.path)
        self.previsoes = RegistoPrevisoes(Path(self.tmp.name)/'previsoes_premium.json')
        self.bot = BotPremiumReal(token='token-de-teste', gestor=self.g, owner_id=10, chat_id=-20, previsoes=self.previsoes)
        self.bot.username = 'ExemploBot'
        self.mensagens = []
        self.bot.enviar_mensagem = lambda chat, text: self.mensagens.append(text)

    def add(self, odd='2.5', stake='10', update_id=None):
        return self.g.adicionar_aposta({'jogo':'A vs B','tipo':'Vitória Casa','odds':odd,'stake':stake}, update_id)

    def command(self, text, user=10, chat=-20, update=None):
        self.bot.processar_comando(chat, text, user, update)

    def test_restore_once_never_overwrites_existing_history(self):
        backup = {'apostas': [{'id': 42, 'jogo': 'A vs B', 'tipo': 'Vitória Casa', 'odds': 2, 'resultado': None}]}
        with patch.dict('os.environ', {'RESTORE_HISTORICO_JSON': json.dumps(backup)}):
            g = GestorApostas(self.path)
            self.assertEqual(g.obter_aposta(42)['jogo'], 'A vs B')
            g.adicionar_aposta({'jogo': 'C vs D', 'tipo': 'Ambas Marcam', 'odds': 2, 'stake': 1})
            self.assertEqual(len(GestorApostas(self.path).dados['apostas']), 2)

    def test_invalid_restore_does_not_create_file(self):
        with patch.dict('os.environ', {'RESTORE_HISTORICO_JSON': '{invalid'}):
            with self.assertRaises(ValueError): GestorApostas(self.path)
        self.assertFalse(self.path.exists())

    def test_lucro_roi_ponderado_anuladas_pendentes(self):
        self.g.registar_resultado(self.add(), 'ganhou')
        self.g.registar_resultado(self.add('1.9','5'), 'perdeu')
        self.g.registar_resultado(self.add('2','20'), 'anulada')
        self.add('2','30')
        s = self.g.calcular_estatisticas()
        self.assertEqual(s['lucro_real'], Decimal('10.00'))
        self.assertEqual(s['valor_liquidado'], Decimal('15'))
        self.assertAlmostEqual(s['roi_medio_real'], 100*10/15)
        self.assertEqual(s['pendentes'], 1)
        self.assertEqual(s['anuladas'], 1)

    def test_legacy_preservado_sem_contas_reais(self):
        self.path.write_text(json.dumps({'apostas':[{'id':8,'jogo':'A vs B','tipo':'Vitória Casa','odds':2,'resultado':'ganhou','roi_real':100}]}))
        g = GestorApostas(self.path)
        self.assertEqual(g.calcular_estatisticas()['lucro_real'], 0)
        self.assertEqual(g.calcular_estatisticas()['legadas'], 1)
        self.assertEqual(g.adicionar_aposta({'jogo':'C vs D','tipo':'Ambas Marcam','odds':2,'stake':1}),9)
        self.assertEqual(len(GestorApostas(self.path).dados['apostas']),2)

    def test_corrupt_file_not_overwritten(self):
        self.path.write_text('{invalid')
        with self.assertRaises(ValueError): GestorApostas(self.path)
        self.assertEqual(self.path.read_text(),'{invalid')

    def test_invalid_money(self):
        for odd, stake in [('1','1'),('NaN','1'),('Infinity','1'),('2','-1'),('2','0.001'),('2','NaN')]:
            with self.subTest(odd=odd,stake=stake):
                with self.assertRaises(ValueError): self.add(odd,stake)
        self.assertEqual(self.g.dados['apostas'],[])

    def test_comma_and_persistence(self):
        self.add('1,9','2,50')
        self.assertEqual(GestorApostas(self.path).obter_aposta(1)['stake'],'2.50')

    def test_write_failure_keeps_disk_and_memory(self):
        self.add()
        original=self.path.read_text()
        with patch('gestor_apostas.os.replace',side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.add()
        self.assertEqual(self.path.read_text(),original)
        self.assertEqual(len(self.g.dados['apostas']),1)

    def test_duplicate_update(self):
        self.assertEqual(self.add(update_id=100),self.add(update_id=100))
        self.assertEqual(len(self.g.dados['apostas']),1)
        self.g.marcar_update(100)
        self.assertEqual(GestorApostas(self.path).dados['ultimo_update'],100)

    def test_owner_and_chat(self):
        self.command('/add_aposta "A vs B" "Vitória Casa" 2 1',user=11)
        self.command('/add_aposta "A vs B" "Vitória Casa" 2 1',chat=-21)
        self.assertEqual(self.g.dados['apostas'],[])
        self.assertEqual(self.mensagens,[])

    def test_group_suffix_and_actual_id(self):
        self.add()
        self.command('/add_aposta@ExemploBot "C vs D" "Ambas Marcam" 1.9 2',update=5)
        self.assertIn('#2', self.mensagens[-1])
        self.command('/score@ExemploBot 2 1-1')
        self.assertEqual(self.g.obter_aposta(2)['resultado'],'ganhou')
        self.command('/add_aposta@OutroBot "E vs F" "Ambas Marcam" 2 1')
        self.assertEqual(len(self.g.dados['apostas']),2)

    def test_settlement_not_silently_overwritten(self):
        i=self.add()
        self.g.registar_resultado(i,'ganhou')
        self.assertTrue(self.g.registar_resultado(i,'ganhou'))
        with self.assertRaises(ValueError): self.g.registar_resultado(i,'perdeu')
        with self.assertRaises(ValueError): self.g.registar_resultado(i,'outro')

    def test_markets_and_final_status(self):
        r=RastreadorResultados()
        for tipo,result in [('Vitória Casa','perdeu'),('Vitória Fora','perdeu'),('Ambas Marcam','ganhou'),('Over 2.5 Golos','perdeu')]:
            self.assertEqual(r.analisar_aposta({'tipo':tipo},{'casa':1,'fora':1,'status':'finished'}),result)
        for s in [{'casa':1,'fora':0,'status':'inprogress'}, {'casa':-1,'fora':0,'status':'finished'}]:
            self.assertIsNone(r.analisar_aposta({'tipo':'Vitória Casa'},s))
        self.assertIsNone(r.analisar_aposta({'tipo':'Cantos'},{'casa':2,'fora':1,'status':'finished'}))

    def test_analysis_does_not_create_bets_or_fake_fallback(self):
        self.bot.buscador.buscar_todos_jogos_hoje = lambda: []
        self.bot.buscador.formatar_jogos = lambda jogos: 'sem jogos reais disponíveis'
        self.command('/analisa')
        self.assertEqual(self.g.dados['apostas'],[])
        self.assertIn('sem jogos reais', self.mensagens[-1])
        self.assertEqual(AnalisadorInteligente().gerar_todas_apostas([{'id':1}]),[])
        with patch.dict('os.environ', {'ENABLE_REAL_GAMES':'0', 'ENABLE_SOFASCORE':'0'}):
            self.assertEqual(BuscadorJogosReais().buscar_todos_jogos_hoje(),[])

    def test_performance_empty_is_safe(self):
        self.command('/performance')
        self.assertIn('Previsões registadas: 0', self.mensagens[-1])

    def test_telegram_text_chunking(self):
        bot=BotPremiumReal(token='teste',gestor=self.g,owner_id=10,chat_id=-20,previsoes=self.previsoes)
        calls=[]
        bot.api=lambda method,data:calls.append(data)
        text='⚽' * 6000 + '<texto>'
        bot.enviar_mensagem(-20,text)
        self.assertEqual(''.join(c['text'] for c in calls),text)
        self.assertTrue(all(len(c['text'].encode('utf-16-le'))//2<=4096 for c in calls))
        self.assertTrue(all('parse_mode' not in c for c in calls))

if __name__=='__main__': unittest.main()
