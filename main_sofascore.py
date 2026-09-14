"""Bot privado de manutenção: registo manual, sem recomendações fabricadas."""
import logging
import os
import re
import shlex
import time
import requests
from gestor_apostas import GestorApostas
from rastreador_resultados import RastreadorResultados
from analisador_inteligente import AnalisadorInteligente
from buscador_jogos_reais import BuscadorJogosReais

AJUDA = '''🤖 BOT DE APOSTAS — VERSÃO DE MANUTENÇÃO
/start ou /ajuda — Ajuda
/id — Ver o teu ID e o ID desta conversa
/jogos — Consultar jogos reais de hoje no SofaScore
/analisa — Estado da análise automática
/add_aposta "Jogo" "Mercado" ODD VALOR — Registar uma aposta já feita
/resultados — Histórico e contas
/score ID ganhou|perdeu|anulada — Registar resultado
/score ID 2-1 — Resultado final no tempo regulamentar (inclui compensação)
/status — Estado do bot

Exemplo de formato (não é uma recomendação):
/add_aposta "Equipa A vs Equipa B" "Over 2.5 Golos" 1.90 1.00

Mercados com interpretação de resultado: Vitória Casa, Vitória Fora,
Ambas Marcam, Over 2.5 Golos e Over 3.5 Golos.
Outros mercados: registar ganhou/perdeu/anulada manualmente.
Usa /score apenas depois da liquidação da aposta.
As apostas não são colocadas na Betano pelo bot.'''

class BotPremiumReal:
    def __init__(self, token=None, gestor=None, owner_id=None, chat_id=None, session=None, buscador=None):
        self.token = token or (os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_TOKEN', '')).strip()
        if not self.token:
            raise ValueError('Configura TELEGRAM_BOT_TOKEN nas variáveis do serviço.')
        self.owner_id = int(owner_id or os.getenv('OWNER_USER_ID', '0'))
        self.chat_id = int(chat_id or os.getenv('ALLOWED_CHAT_ID', '0'))
        self.base_url = f'https://api.telegram.org/bot{self.token}'
        self.gestor = gestor or GestorApostas()
        self.rastreador = RastreadorResultados()
        self.session = session or requests.Session()
        self.buscador = buscador or BuscadorJogosReais()
        self.username = None

    def api(self, metodo, data):
        # Não registar exceções requests: podem incluir o token no URL.
        r = self.session.post(f'{self.base_url}/{metodo}', json=data, timeout=(5, 40))
        if r.status_code != 200:
            raise RuntimeError(f'Telegram HTTP {r.status_code}')
        payload = r.json()
        if not payload.get('ok'):
            raise RuntimeError('O Telegram recusou o pedido.')
        return payload['result']

    def enviar_mensagem(self, chat_id, texto):
        # Texto simples; blocos pequenos também com emojis de duas unidades UTF-16.
        for i in range(0, len(texto), 1800):
            self.api('sendMessage', {'chat_id': chat_id, 'text': texto[i:i+1800]})

    def processar_comando(self, chat_id, texto, user_id=None, update_id=None):
        comando, _, argumentos = texto.strip().partition(' ')
        if '@' in comando:
            comando, alvo = comando.split('@', 1)
            if self.username is None or alvo.lower() != self.username.lower():
                return
        if comando == '/id':
            self.enviar_mensagem(chat_id, f'ID utilizador: {user_id}\nID conversa: {chat_id}')
            return
        if not self.owner_id or not self.chat_id or chat_id != self.chat_id or user_id != self.owner_id:
            return
        try:
            if comando in ('/start', '/ajuda'):
                resposta = AJUDA
            elif comando == '/jogos':
                jogos = self.buscador.buscar_todos_jogos_hoje()
                resposta = self.buscador.formatar_jogos(jogos)
            elif comando == '/analisa':
                resposta = (
                    AnalisadorInteligente.motivo_indisponivel
                    + '\n\nJá existe um conector SofaScore para validar jogos reais com /jogos. '
                    'A fase seguinte é integrar odds Betano Portugal e o modelo estatístico.'
                )
            elif comando == '/status':
                resposta = (
                    'Bot de manutenção ativo.\n'
                    'Registo manual ativo.\n'
                    'SofaScore: conector instalado; valida com /jogos.\n'
                    'Odds Betano: ainda não configuradas.\n'
                    'Análise automática: ainda suspensa até validar odds e modelo.\n'
                    'Liquidação automática: desativada.'
                )
            elif comando == '/resultados':
                resposta = self.gestor.gerar_relatorio()
            elif comando == '/add_aposta':
                partes = shlex.split(argumentos)
                if len(partes) != 4:
                    raise ValueError('Usa /add_aposta "Jogo" "Mercado" ODD VALOR')
                jogo, tipo, odd, stake = partes
                ident = self.gestor.adicionar_aposta({'jogo': jogo, 'tipo': tipo, 'odds': odd, 'stake': stake}, update_id)
                resposta = f'Aposta #{ident} registada. Consulta /resultados.'
            elif comando == '/score':
                partes = argumentos.split()
                if len(partes) != 2:
                    raise ValueError('Usa /score ID ganhou|perdeu|anulada ou /score ID 2-1.')
                ident, resultado = int(partes[0]), partes[1].lower()
                aposta = self.gestor.obter_aposta(ident)
                if aposta is None:
                    raise ValueError('Aposta não encontrada.')
                if re.fullmatch(r'\d{1,2}-\d{1,2}', resultado):
                    casa, fora = map(int, resultado.split('-'))
                    resultado = self.rastreador.analisar_aposta(aposta, {'status': 'finished', 'casa': casa, 'fora': fora})
                    if resultado is None:
                        raise ValueError('Mercado não suportado por marcador. Regista o resultado manualmente.')
                self.gestor.registar_resultado(ident, resultado)
                resposta = f'Aposta #{ident}: {resultado}.'
            else:
                resposta = 'Comando desconhecido. Usa /ajuda.'
        except (ValueError, KeyError, ArithmeticError):
            # Mensagem fixa: nenhum dado sensível em detalhes de erros.
            resposta = 'Não foi possível aceitar o comando. Verifica o formato em /ajuda, o ID e se o resultado já foi registado. O histórico não foi alterado.'
        self.enviar_mensagem(chat_id, resposta)

    def buscar_atualizacoes(self):
        self.username = self.api('getMe', {})['username']
        if self.api('getWebhookInfo', {}).get('url'):
            raise RuntimeError('Existe um webhook configurado. Resolver antes de usar polling.')
        while True:
            try:
                updates = self.api('getUpdates', {'offset': self.gestor.dados.get('ultimo_update', 0)+1, 'timeout': 30, 'allowed_updates': ['message']})
                for update in updates:
                    msg = update.get('message', {})
                    texto = msg.get('text', '').strip()
                    if texto.startswith('/'):
                        self.processar_comando(msg['chat']['id'], texto, msg.get('from', {}).get('id'), update['update_id'])
                    self.gestor.marcar_update(update['update_id'])
            except (requests.RequestException, RuntimeError, ValueError):
                logging.warning('Falha na comunicação Telegram; nova tentativa em 5 segundos.')
                time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        BotPremiumReal().buscar_atualizacoes()
    except Exception:
        logging.error('Arranque ou escrita interrompidos. Verifica configuração, histórico e permissões; detalhes omitidos para proteger credenciais.')
        raise SystemExit(1)

if __name__ == '__main__':
    main()
