"""Bot privado: jogos reais, análise premium beta e registo de apostas."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
from odds_auditoria import AuditoriaOdds
from odds_betano import OddsBetano
from previsoes_premium import RegistoPrevisoes

AJUDA = '''🤖 BOT DE APOSTAS — PREMIUM BETA
/start ou /ajuda — Ajuda
/id — Ver o teu ID e o ID desta conversa
/jogos — Consultar jogos reais de hoje (hora de Portugal; ESPN + fallback SofaScore)
/analisa — Relatório premium compacto dos jogos de hoje
/analisa_full — Relatório técnico completo do mesmo modelo
/performance — Liquidar previsões passadas e mostrar auditoria do modelo
/odds — Listar eventos com odds Betano, se uma fonte de odds estiver configurada
/odds ID — Consultar mercados/odds Betano desse evento
/add_aposta "Jogo" "Mercado" ODD VALOR — Registar uma aposta já feita
/resultados — Histórico e contas
/score ID ganhou|perdeu|anulada — Registar resultado
/score ID 2-1 — Resultado final no tempo regulamentar (inclui compensação)
/status — Estado do bot

No /analisa, a odd mínima é o preço a partir do qual o modelo aponta para uma margem teórica de 5%.
As previsões ficam guardadas antes do jogo para auditoria; não são reescritas depois.
ROI/EV só são mostrados quando existirem odds reais guardadas no momento da previsão.
As probabilidades são estimativas estatísticas e não garantias.
As apostas não são colocadas na Betano pelo bot.'''


class BotPremiumReal:
    ODDS_AUTO_INTERVALO_SEG = 30 * 60
    ODDS_AUTO_JANELA_SEG = 6 * 60 * 60
    JOGOS_RETRY_VAZIO_SEG = 1.0

    def __init__(self, token=None, gestor=None, owner_id=None, chat_id=None, session=None, buscador=None, odds=None, analisador=None, previsoes=None):
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
        self.previsoes = previsoes or RegistoPrevisoes()
        self.username = None
        self._proxima_captura_odds = 0.0

    def api(self, metodo, data):
        r = self.session.post(f'{self.base_url}/{metodo}', json=data, timeout=(5, 40))
        if r.status_code != 200:
            raise RuntimeError(f'Telegram HTTP {r.status_code}')
        payload = r.json()
        if not payload.get('ok'):
            raise RuntimeError('O Telegram recusou o pedido.')
        return payload['result']

    @staticmethod
    def _telegram_units(texto):
        return len(texto.encode('utf-16-le')) // 2

    @classmethod
    def _cortar_bloco(cls, texto, limite):
        partes, atual, unidades = [], [], 0
        for char in texto:
            u = 2 if ord(char) > 0xFFFF else 1
            if atual and unidades + u > limite:
                partes.append(''.join(atual))
                atual, unidades = [], 0
            atual.append(char)
            unidades += u
        if atual:
            partes.append(''.join(atual))
        return partes

    @classmethod
    def _dividir_texto(cls, texto, limite=3900):
        """Divide preferencialmente entre cartões/parágrafos."""
        if cls._telegram_units(texto) <= limite:
            return [texto]

        saida, atual = [], ''
        paragrafos = texto.split('\n\n')
        for paragrafo in paragrafos:
            bloco = paragrafo if not atual else '\n\n' + paragrafo
            if cls._telegram_units(atual + bloco) <= limite:
                atual += bloco
                continue
            if atual:
                saida.append(atual)
                atual = ''
            if cls._telegram_units(paragrafo) <= limite:
                atual = paragrafo
                continue
            linhas = paragrafo.splitlines(keepends=True)
            parcial = ''
            for linha in linhas:
                if cls._telegram_units(parcial + linha) <= limite:
                    parcial += linha
                    continue
                if parcial:
                    saida.append(parcial.rstrip('\n'))
                    parcial = ''
                if cls._telegram_units(linha) <= limite:
                    parcial = linha
                else:
                    saida.extend(cls._cortar_bloco(linha, limite))
            atual = parcial.rstrip('\n')
        if atual:
            saida.append(atual)
        return [p for p in saida if p]

    @staticmethod
    def _filtrar_data_portugal(jogos, data_iso=None):
        """Mantém apenas eventos cuja data em Europe/Lisbon corresponde ao dia pedido."""
        alvo = data_iso or datetime.now(ZoneInfo('Europe/Lisbon')).strftime('%Y-%m-%d')
        saida = []
        for jogo in jogos or []:
            ts = jogo.get('timestamp') if isinstance(jogo, dict) else None
            if not isinstance(ts, (int, float)):
                continue
            data_local = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
                ZoneInfo('Europe/Lisbon')
            ).strftime('%Y-%m-%d')
            if data_local == alvo:
                saida.append(jogo)
        return saida

    def _jogos_hoje_portugal(self):
        data_iso = datetime.now(ZoneInfo('Europe/Lisbon')).strftime('%Y-%m-%d')
        for tentativa in range(2):
            jogos = self.buscador.buscar_todos_jogos_hoje(data_iso)
            filtrados = self._filtrar_data_portugal(jogos, data_iso)
            if filtrados:
                return filtrados
            if tentativa == 0:
                logging.warning(
                    'JOGOS | listagem vazia na primeira tentativa; repetir em %.1fs',
                    self.JOGOS_RETRY_VAZIO_SEG,
                )
                time.sleep(self.JOGOS_RETRY_VAZIO_SEG)
        return []

    def _executar_analise(self, tecnica=False):
        jogos = self._jogos_hoje_portugal()
        if not jogos:
            return self.buscador.formatar_jogos(jogos)
        selecoes = self.analisador.gerar_todas_apostas(jogos)
        try:
            selecoes = AuditoriaOdds(self.odds).enriquecer(selecoes)
        except (RuntimeError, ValueError, TypeError):
            # Odds são opcionais; falhas nesta camada nunca bloqueiam a V1.
            pass
        if tecnica:
            resposta = self.analisador.gerar_relatorio_tecnico(jogos, selecoes=selecoes)
        else:
            resposta = self.analisador.gerar_relatorio(jogos, selecoes=selecoes)
        novas = self.previsoes.registar(selecoes)
        if novas:
            resposta += f'\n\n🧾 Auditoria: {novas} nova(s) previsão(ões) guardada(s) antes dos jogos.'
        return resposta

    def _selecoes_sem_odd_proximas(self):
        """Reconstrói snapshots pendentes sem odd, apenas antes do início do jogo."""
        if not self.odds.configurada:
            return []

        agora = datetime.now(ZoneInfo('Europe/Lisbon'))
        agora_ts = agora.timestamp()
        limite_ts = agora_ts + self.ODDS_AUTO_JANELA_SEG
        data_iso = agora.strftime('%Y-%m-%d')
        selecoes = []

        for p in self.previsoes.dados.get('previsoes', []):
            if p.get('data_jogo') != data_iso or p.get('estado') != 'pendente':
                continue
            if self.previsoes._odd_real_valida(p.get('odd_real')) is not None:
                continue
            ts = p.get('timestamp_jogo')
            if not isinstance(ts, (int, float)):
                continue
            if float(ts) <= agora_ts or float(ts) > limite_ts:
                continue
            try:
                prob = float(p['probabilidade'])
                qualidade = int(p['qualidade'])
                odd_justa = float(p['odd_justa'])
                odd_minima = float(p['odd_minima'])
            except (KeyError, TypeError, ValueError):
                continue

            selecoes.append(
                {
                    'jogo': {
                        'id': p.get('event_id'),
                        'casa': p.get('casa') or '?',
                        'fora': p.get('fora') or '?',
                        'liga': p.get('liga') or 'Competição',
                        'timestamp': ts,
                    },
                    'mercado': p.get('mercado') or 'Mercado desconhecido',
                    'probabilidade': prob,
                    'qualidade': qualidade,
                    'odd_justa': odd_justa,
                    'odd_minima': odd_minima,
                }
            )
        return selecoes

    def _capturar_odds_pendentes(self):
        """Anexa a primeira odd válida aos snapshots; nunca recria previsões."""
        selecoes = self._selecoes_sem_odd_proximas()
        if not selecoes:
            return 0

        antes = sum(
            1
            for p in self.previsoes.dados.get('previsoes', [])
            if self.previsoes._odd_real_valida(p.get('odd_real')) is not None
        )
        enriquecidas = AuditoriaOdds(self.odds).enriquecer(selecoes)
        self.previsoes.registar(enriquecidas)
        depois = sum(
            1
            for p in self.previsoes.dados.get('previsoes', [])
            if self.previsoes._odd_real_valida(p.get('odd_real')) is not None
        )
        capturadas = max(depois - antes, 0)
        if capturadas:
            logging.info('ODDS_AUTO | %s odd(s) congelada(s) antes do jogo', capturadas)
        return capturadas

    def _capturar_odds_se_devida(self):
        """Executa no máximo uma ronda a cada 30 minutos."""
        agora = time.monotonic()
        if agora < self._proxima_captura_odds:
            return 0
        self._proxima_captura_odds = agora + self.ODDS_AUTO_INTERVALO_SEG
        if not self.odds.configurada:
            return 0
        try:
            return self._capturar_odds_pendentes()
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            logging.warning('ODDS_AUTO | ronda automática indisponível; tenta novamente mais tarde')
            return 0

    def enviar_mensagem(self, chat_id, texto):
        for parte in self._dividir_texto(texto):
            self.api('sendMessage', {'chat_id': chat_id, 'text': parte})

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
                jogos = self._jogos_hoje_portugal()
                resposta = self.buscador.formatar_jogos(jogos)
            elif comando == '/analisa':
                resposta = self._executar_analise(tecnica=False)
            elif comando == '/analisa_full':
                resposta = self._executar_analise(tecnica=True)
            elif comando == '/performance':
                liquidadas = self.previsoes.atualizar_pendentes()
                resposta = self.previsoes.relatorio()
                if liquidadas:
                    resposta = f'🔄 {liquidadas} previsão(ões) liquidada(s) agora.\n\n' + resposta
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
                    'Data dos jogos: filtrada por hora de Portugal (Europe/Lisbon).\n'
                    f'Odds Betano: {self.odds.nome_fonte if self.odds.configurada else "opcionais / não configuradas"}.\n'
                    'Análise premium: ativa com histórico ESPN + modelo Poisson.\n'
                    'Apresentação: /analisa compacto + /analisa_full técnico.\n'
                    'Filtro: amostra mínima + qualidade dos dados + probabilidade conservadora + odd mínima alvo.\n'
                    'Auditoria de previsões: ativa e persistente em /data.\n'
                    'Captura automática de odds: ativa para previsões pendentes próximas do início.\n'
                    'ROI do modelo: calculado apenas nas previsões com odd real congelada.'
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
        except (ValueError, KeyError, ArithmeticError, OSError):
            resposta = 'Não foi possível aceitar o comando. Verifica o formato em /ajuda, o ID e os dados disponíveis. O histórico não foi alterado.'
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
                self._capturar_odds_se_devida()
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
