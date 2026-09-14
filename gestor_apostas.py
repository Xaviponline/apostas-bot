"""Histórico local de uma banca privada; escrita atómica, sem inferir stakes antigas."""
import copy
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo


def numero(valor):
    try:
        n = Decimal(str(valor).replace(',', '.'))
    except InvalidOperation:
        raise ValueError('Número inválido.') from None
    if not n.is_finite():
        raise ValueError('Número inválido.')
    return n


def agora():
    return datetime.now(ZoneInfo('Europe/Lisbon')).isoformat(timespec='seconds')


class GestorApostas:
    def __init__(self, ficheiro=None):
        self.ficheiro_apostas = Path(ficheiro or Path(os.getenv('DATA_DIR', '.')) / 'apostas_historico.json')
        self.dados = {'apostas': [], 'ultimo_update': 0}
        backup = os.getenv('RESTORE_HISTORICO_JSON')
        if not self.ficheiro_apostas.exists() and backup:
            dados = json.loads(backup)
            if not isinstance(dados, dict) or not isinstance(dados.get('apostas'), list):
                raise ValueError('Cópia de segurança inválida.')
            ids = [a['id'] for a in dados['apostas']]
            if len(ids) != len(set(ids)):
                raise ValueError('Cópia de segurança com IDs duplicados.')
            self._commit(dados)
        if self.ficheiro_apostas.exists():
            # Histórico inválido interrompe o arranque: nunca o substituir por uma lista vazia.
            self.dados = json.loads(self.ficheiro_apostas.read_text(encoding='utf-8'))
            if not isinstance(self.dados, dict) or not isinstance(self.dados.get('apostas'), list):
                raise ValueError('Histórico inválido. Restaurar uma cópia antes de arrancar.')
            ids = [a['id'] for a in self.dados['apostas']]
            if len(ids) != len(set(ids)):
                raise ValueError('Histórico com IDs duplicados.')

    def _commit(self, dados):
        pasta = self.ficheiro_apostas.parent
        pasta.mkdir(parents=True, exist_ok=True)
        fd, nome = tempfile.mkstemp(dir=pasta, prefix='.apostas-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(dados, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(nome, self.ficheiro_apostas)
        finally:
            if os.path.exists(nome):
                os.unlink(nome)
        self.dados = dados

    def marcar_update(self, update_id):
        dados = copy.deepcopy(self.dados)
        dados['ultimo_update'] = update_id
        self._commit(dados)

    def adicionar_aposta(self, aposta_dict, update_id=None):
        # A chave Telegram evita duplicados se houver um reinício antes de confirmar o offset.
        for a in self.dados['apostas']:
            if update_id is not None and a.get('update_id') == update_id:
                return a['id']
        odd, stake = numero(aposta_dict['odds']), numero(aposta_dict['stake'])
        if odd <= 1 or stake <= 0 or stake != stake.quantize(Decimal('.01')):
            raise ValueError('Odd superior a 1 e valor positivo com até 2 casas decimais.')
        jogo, tipo = aposta_dict['jogo'].strip(), aposta_dict['tipo'].strip()
        if not jogo or not tipo or len(jogo) > 200 or len(tipo) > 100:
            raise ValueError('Jogo ou mercado vazio/demasiado longo.')
        dados = copy.deepcopy(self.dados)
        aposta_id = max((a['id'] for a in dados['apostas']), default=0) + 1
        dados['apostas'].append({
            'id': aposta_id, 'data': agora(), 'jogo': jogo, 'tipo': tipo,
            'odds': str(odd), 'stake': str(stake), 'origem': 'manual',
            'resultado': None, 'data_resultado': None, 'update_id': update_id,
        })
        self._commit(dados)
        return aposta_id

    def obter_aposta(self, aposta_id):
        return next((a for a in self.dados['apostas'] if a['id'] == aposta_id), None)

    def registar_resultado(self, aposta_id, resultado):
        if resultado not in ('ganhou', 'perdeu', 'anulada'):
            raise ValueError('Resultado inválido.')
        aposta = self.obter_aposta(aposta_id)
        if aposta is None:
            return False
        if aposta.get('origem') != 'manual':
            raise ValueError('Registo antigo não confirmado; excluído das contas reais.')
        if aposta.get('resultado') is not None:
            if aposta['resultado'] == resultado:
                return True
            raise ValueError('Resultado já registado; não foi alterado.')
        dados = copy.deepcopy(self.dados)
        a = next(a for a in dados['apostas'] if a['id'] == aposta_id)
        a['resultado'], a['data_resultado'] = resultado, agora()
        self._commit(dados)
        return True

    def obter_apostas_pendentes(self):
        return [a for a in self.dados['apostas'] if a.get('origem') == 'manual' and a.get('resultado') is None]

    def calcular_estatisticas(self, apostas=None):
        todos = self.dados['apostas'] if apostas is None else apostas
        reais = [a for a in todos if a.get('origem') == 'manual' and a.get('stake') is not None]
        liquidadas = [a for a in reais if a.get('resultado') in ('ganhou', 'perdeu')]
        total = sum((numero(a['stake']) for a in liquidadas), Decimal(0))
        lucro = sum((numero(a['stake']) * (numero(a['odds']) - 1) if a['resultado'] == 'ganhou' else -numero(a['stake']) for a in liquidadas), Decimal(0))
        ganhas = sum(a['resultado'] == 'ganhou' for a in liquidadas)
        return {
            'total': len(reais), 'ganhas': ganhas, 'perdidas': len(liquidadas)-ganhas,
            'pendentes': sum(a.get('resultado') is None for a in reais),
            'anuladas': sum(a.get('resultado') == 'anulada' for a in reais),
            'legadas': len(todos)-len(reais),
            'win_rate': round(100*ganhas/len(liquidadas), 1) if liquidadas else 0,
            'roi_medio_real': float(lucro/total*100) if total else 0,
            'lucro_real': lucro.quantize(Decimal('.01'), rounding=ROUND_HALF_UP),
            'valor_liquidado': total,
        }

    def gerar_relatorio(self):
        s = self.calcular_estatisticas()
        linhas = ['📊 HISTÓRICO DE APOSTAS REGISTADAS',
                  f"Ganhas: {s['ganhas']} | Perdidas: {s['perdidas']} | Anuladas: {s['anuladas']}",
                  f"Pendentes: {s['pendentes']} | Taxa de acerto: {s['win_rate']}%",
                  f"Valor liquidado (sem anuladas): {s['valor_liquidado']:.2f} €",
                  f"Lucro: {s['lucro_real']:+.2f} € | ROI: {s['roi_medio_real']:+.2f}%",
                  f"Registos antigos sem confirmação, fora das contas: {s['legadas']}",
                  'Resultados introduzidos pelo utilizador; sem verificação na Betano.', '\nÚltimos 10 registos:']
        for a in self.dados['apostas'][-10:]:
            linhas.append(f"#{a['id']} {a['jogo']} | {a['tipo']} @{a['odds']} | {a.get('stake', '?')} € | {a.get('resultado') or 'pendente'}")
        return '\n'.join(linhas)
