"""Bot privado: jogos reais, análise premium beta e registo de apostas."""
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
from odds_betano import OddsBetano

AJUDA = '''🤖 BOT DE APOSTAS — PREMIUM BETA
/start ou /ajuda — Ajuda
/id — Ver o teu ID e o ID desta conversa
/jogos — Consultar jogos reais de hoje (ESPN + fallback SofaScore)
/analisa — Analisar os jogos de hoje com estatísticas reais e modelo Poisson
/odds — Listar eventos com odds Betano, se uma fonte de odds estiver configurada
/odds ID — Consultar mercados/odds Betano desse evento
/add_aposta "Jogo" "Mercado" ODD VALOR — Registar uma aposta já feita
/resultados — Histórico e contas
/score ID ganhou|perdeu|anulada — Registar resultado
/score ID 2-1 — Resultado final no tempo regulamentar (inclui compensação)
/status — Estado do bot

No /analisa, a odd mínima é o preço a partir do qual o modelo aponta para uma margem teórica de 5%.
As probabilidades são estimativas estatísticas e não garantias.
As apostas não são colocadas na Betano pelo bot.'''


class BotPremiumReal:
    def __init__(self, token=None, gestor=None, owner_id=None, chat_id=None, session=None, buscador=None, odds=None, analisador=None):
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
        self.odds = odds or OddsBetano()
        self.analisador = analisador or AnalisadorInteligente(self.buscador)
        self.username = None

    def api(self, metodo, data):
        r = self.session.post(f'{self.base_url}/{metodo}', json=data, timeout=(5, 40))
        if r.status_code != 200:
            raise RuntimeError(f'Telegram HTTP {r.status_code}')
        payload = r.json()
        if not payload.get('ok'):
            raise RuntimeError('O Telegram recusou o pedido.')
        return payload['result']

    def enviar_mensagem(self, chat_id, texto):
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
                jogos = self.buscador.buscar_todos_jogos_hoje()
                if not jogos:
                    resposta = self.buscador.formatar_jogos(jogos)
                else:
                    resposta = self.analisador.gerar_relatorio(jogos)
            elif comando == '/odds':
                if not self.odds.configurada:
                    resposta = (
                        'Odds Betano ainda não configuradas. '
                        'O /analisa funciona sem elas e indica odd justa e odd mínima.'
                    )
                elif argumentos.strip():
                    evento_id = argumentos.strip()
                    resposta = self.odds.formatar_odds(self.odds.odds_evento(evento_id))
                else:
                    resposta = self.odds.formatar_eventos(self.odds.eventos_hoje())
            elif comando == '/status':
                resposta = (
                    'Bot premium beta ativo.\n'
                    'Registo manual ativo.\n'
                    f'Jogos reais: {self.buscador.fonte or "ESPN principal + SofaScore fallback"}.\n'
                    f'Odds Betano: {self.odds.nome_fonte if self.odds.configurada else "opcionais / não configuradas"}.\n'
                    'Análise premium: ativa com histórico ESPN + modelo Poisson.\n'
                    'Filtro: amostra mínima + qualidade dos dados + odd mínima alvo.\n'
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
            resposta = 'Não foi possível aceitar o comando. Verifica o formato em /ajuda, o ID e se o resultado já foi registado. O histórico não foi alterado.'
        self.enviar_mensagem(chat_id, resposta)

    def buscar_atualizacoes(self):
        self.username = self.api('getMe', {})['username']
        if self.api('getWebhookInfo', {}).get('url'):
            raise RuntimeError('Existe um webhook configurado. Resolver antes de usar polling.')
        while True:
            try:
                updates = self.api('getUpdates', {
                    'offset': self.gestor.dados.get('ultimo_update', 0) + 1,
                    'timeout': 30,
                    'allowed_updates': ['message'],
                })
                for update in updates:
                    msg = update.get('message', {})
                    texto = msg.get('text', '').strip()
                    if texto.startswith('/'):
                        self.processar_comando(
                            msg['chat']['id'],
                            texto,
                            msg.get('from', {}).get('id'),
                            update['update_id'],
                        )
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
