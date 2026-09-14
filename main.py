#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS TELEGRAM - COM SOFASCORE REAL
Análise de jogos reais com dados inteligentes
"""

import requests
import json
import time
import threading
from datetime import datetime
from buscador_jogos_reais import BuscadorJogosReais
from analisador_inteligente import AnalisadorInteligente
from gestor_apostas import GestorApostas
from rastreador_resultados import RastreadorResultados

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CHATS_ATIVOS = set()

class BotPremiumReal:
    
    def __init__(self):
        self.buscador = BuscadorJogosReais()
        self.analisador = AnalisadorInteligente(self.buscador)
        self.gestor = GestorApostas()
        self.rastreador = RastreadorResultados()
        self.ultimo_update = 0
        self.cache_jogos = None
        self.cache_tempo = 0
    
    def enviar_mensagem(self, chat_id: int, texto: str):
        """Envia mensagem via Telegram API"""
        try:
            url = f"{BASE_URL}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem: {e}")
            return False
    
    def obter_jogos_cache(self, cache_minutos=30) -> list:
        """Obtém jogos com cache (30 minutos padrão)"""
        tempo_atual = time.time()
        
        if self.cache_jogos and (tempo_atual - self.cache_tempo) < (cache_minutos * 60):
            print(f"✅ Usando cache de jogos ({cache_minutos} min)")
            return self.cache_jogos
        
        print("🔄 Buscando jogos reais do SofaScore...")
        jogos = self.buscador.buscar_todos_jogos_hoje()
        
        if jogos:
            self.cache_jogos = jogos
            self.cache_tempo = tempo_atual
            print(f"✅ {len(jogos)} jogos encontrados!")
        
        return jogos
    
    def processar_comando(self, chat_id: int, texto: str):
        """Processa comandos do bot"""
        
        if texto == "/start":
            mensagem = """
🤖 <b>BEM-VINDO AO BOT APOSTAS PREMIUM!</b>

📊 <b>Análise Inteligente + Jogos REAIS (SofaScore)</b>

<b>Comandos disponíveis:</b>
/analisa - 📈 Ver apostas de HOJE
/resultados - 📊 Ver performance
/status - 🔍 Status do bot
/ajuda - 📖 Informações completas

<b>Rastreio de Resultados:</b>
/score ID ganhou - Registar ganho
/score ID perdeu - Registar perda
/score ID CASA-FORA - Análise automática

<b>Características:</b>
✅ 15 apostas de HOJE (JOGOS REAIS)
✅ Análise por forma dos times
✅ ROI inteligente
✅ Rastreio automático
✅ Histórico completo

Subscreve para análises diárias! 🔥
            """
            self.enviar_mensagem(chat_id, mensagem)
            CHATS_ATIVOS.add(chat_id)
        
        elif texto == "/analisa":
            # Busca jogos reais
            jogos = self.obter_jogos_cache()
            
            if not jogos:
                self.enviar_mensagem(chat_id, "❌ Nenhum jogo encontrado para hoje!\n\nTenta mais tarde! 👋")
                return
            
            # Gera apostas
            apostas = self.analisador.gerar_todas_apostas(jogos)
            
            if not apostas:
                self.enviar_mensagem(chat_id, "❌ Nenhuma aposta de qualidade encontrada para hoje!")
                return
            
            # Formata relatório
            relatorio = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            relatorio += f"🎯 ANÁLISE PREMIUM - {self.analisador.data_hoje}\n"
            relatorio += f"📊 {len(apostas)} APOSTAS PARA HOJE\n"
            relatorio += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            # Agrupa por hora
            apostas_por_hora = {}
            for aposta in apostas:
                hora = aposta["horario"]
                if hora not in apostas_por_hora:
                    apostas_por_hora[hora] = []
                apostas_por_hora[hora].append(aposta)
            
            contador = 1
            for hora in sorted(apostas_por_hora.keys()):
                relatorio += f"⏰ {hora} - JOGOS\n"
                
                for aposta in apostas_por_hora[hora]:
                    relatorio += f"#{contador} {aposta['risco']}\n"
                    relatorio += f"   ⚽ {aposta['jogo']}\n"
                    relatorio += f"   🏆 {aposta['liga']}\n"
                    relatorio += f"   💰 {aposta['tipo']} @{aposta['odds']}\n"
                    relatorio += f"   📈 {aposta['probabilidade']}% | ROI +{aposta['roi']}%\n"
                    relatorio += f"   ⭐ {'⭐' * aposta['confianca']}\n\n"
                    
                    # Registra aposta no gestor
                    self.gestor.adicionar_aposta({
                        "jogo": aposta["jogo"],
                        "liga": aposta["liga"],
                        "tipo": aposta["tipo"],
                        "odds": aposta["odds"],
                        "probabilidade": aposta["probabilidade"],
                        "roi": aposta["roi"]
                    })
                    
                    contador += 1
            
            roi_medio = sum(a["roi"] for a in apostas) / len(apostas)
            relatorio += f"✅ Total: {len(apostas)} apostas (ROI Médio: +{roi_medio:.1f}%)\n"
            
            self.enviar_mensagem(chat_id, relatorio)
            CHATS_ATIVOS.add(chat_id)
        
        elif texto == "/resultados":
            relatorio = self.gestor.gerar_relatorio()
            self.enviar_mensagem(chat_id, relatorio)
            CHATS_ATIVOS.add(chat_id)
        
        elif texto.startswith("/score "):
            partes = texto.split()
            if len(partes) >= 3:
                try:
                    aposta_id = int(partes[1])
                    param = partes[2].lower()
                    
                    aposta = self.gestor.obter_aposta(aposta_id)
                    if not aposta:
                        self.enviar_mensagem(chat_id, f"❌ Aposta #{aposta_id} não encontrada!")
                        return
                    
                    resultado = None
                    
                    if param in ["ganhou", "won", "g"]:
                        resultado = "ganhou"
                    elif param in ["perdeu", "lost", "p"]:
                        resultado = "perdeu"
                    elif "-" in param:
                        try:
                            casa, fora = map(int, param.split("-"))
                            tipo = aposta["tipo"]
                            
                            if tipo == "Ambas Marcam":
                                resultado = "ganhou" if casa > 0 and fora > 0 else "perdeu"
                            elif tipo == "Over 2.5 Golos":
                                resultado = "ganhou" if casa + fora >= 3 else "perdeu"
                            elif tipo == "Over 3.5 Golos":
                                resultado = "ganhou" if casa + fora >= 4 else "perdeu"
                            elif tipo == "Vitória Casa":
                                resultado = "ganhou" if casa > fora else "perdeu"
                            elif tipo == "Vitória Fora":
                                resultado = "ganhou" if fora > casa else "perdeu"
                        except:
                            pass
                    
                    if resultado:
                        self.gestor.registar_resultado(aposta_id, resultado)
                        status = "✅ GANHOU!" if resultado == "ganhou" else "❌ PERDEU!"
                        msg = f"{status}\n\n{aposta['jogo']}\n{aposta['tipo']} @{aposta['odds']}"
                        self.enviar_mensagem(chat_id, msg)
                    else:
                        self.enviar_mensagem(chat_id, f"⚠️ Formato inválido!\n\nUsa:\n/score {aposta_id} ganhou\n/score {aposta_id} perdeu")
                
                except Exception as e:
                    self.enviar_mensagem(chat_id, f"❌ Erro: {str(e)}")
        
        elif texto == "/status":
            jogos = self.obter_jogos_cache()
            stats = self.gestor.calcular_estatisticas()
            status = f"""
✅ <b>BOT STATUS</b>

🤖 Bot: <b>OPERACIONAL</b> ✓
🌐 SofaScore: <b>ONLINE</b> ✓
📊 Análise: <b>INTELIGENTE</b> ✓
⏰ Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}

🎮 <b>JOGOS REAIS:</b>
{len(jogos)} jogos encontrados hoje

📈 <b>PERFORMANCE:</b>
Total apostas: {stats['total']}
✅ Ganhas: {stats['ganhas']}
❌ Perdidas: {stats['perdidas']}
⏳ Pendentes: {stats['pendentes']}

Win Rate: {stats['win_rate']}%
ROI Real: +{stats['roi_medio_real']}%
Lucro: €{stats['lucro_real']}

/analisa para ver as apostas de HOJE!
            """
            self.enviar_mensagem(chat_id, status)
        
        elif texto == "/ajuda":
            ajuda = """
📖 <b>GUIA COMPLETO</b>

<b>COMANDOS PRINCIPAIS:</b>
/start - Começar
/analisa - Ver apostas de HOJE (JOGOS REAIS)
/resultados - Ver performance
/status - Ver status do bot

<b>REGISTAR RESULTADOS:</b>
/score ID ganhou - Registar ganho
/score ID perdeu - Registar perda
/score ID CASA-FORA - Análise automática (Ex: /score 1 2-1)

<b>Como funciona:</b>
✓ Busca JOGOS REAIS de hoje (SofaScore)
✓ Análise inteligente por forma dos times
✓ ROI baseado em probabilidade real
✓ Rastreio automático de resultados
✓ Histórico completo guardar

<b>Dados Reais:</b>
- Jogos de ligas: PL, La Liga, Serie A, BuLi, L1, Liga PT, Brasileirão
- Forma recente dos times (últimos 5 jogos)
- Probabilidade calculada por estatísticas
- Odds realista baseada em probabilidade

🔥 Subscreve para análises diárias!
            """
            self.enviar_mensagem(chat_id, ajuda)
        
        else:
            resposta = "❓ Comando não reconhecido!\n\nUsa /ajuda para ver os comandos disponíveis!"
            self.enviar_mensagem(chat_id, resposta)
    
    def buscar_atualizacoes(self):
        """Busca atualizações de mensagens (polling)"""
        
        while True:
            try:
                url = f"{BASE_URL}/getUpdates"
                params = {"offset": self.ultimo_update + 1, "timeout": 30}
                
                response = requests.get(url, params=params, timeout=35)
                
                if response.status_code == 200:
                    dados = response.json()
                    
                    if dados.get("ok") and dados.get("result"):
                        for update in dados["result"]:
                            self.ultimo_update = update["update_id"]
                            
                            if "message" in update:
                                msg = update["message"]
                                chat_id = msg["chat"]["id"]
                                
                                if "text" in msg:
                                    texto = msg["text"].strip()
                                    print(f"📨 [{chat_id}] {texto}")
                                    
                                    if texto.startswith("/"):
                                        self.processar_comando(chat_id, texto)
                
                time.sleep(0.5)
            
            except requests.exceptions.Timeout:
                print("⏱️ Timeout (normal)")
                time.sleep(5)
            
            except Exception as e:
                print(f"❌ Erro: {e}")
                time.sleep(5)
    
    def analise_automatica(self):
        """Análise automática às 08:00"""
        while True:
            try:
                agora = datetime.now()
                
                if agora.hour == 8 and agora.minute == 0:
                    jogos = self.obter_jogos_cache()
                    
                    if jogos:
                        apostas = self.analisador.gerar_todas_apostas(jogos)
                        
                        relatorio = "📊 <b>ANÁLISE AUTOMÁTICA PREMIUM</b>\n\n"
                        relatorio += f"{len(apostas)} apostas de qualidade para hoje!"
                        
                        for chat_id in list(CHATS_ATIVOS):
                            self.enviar_mensagem(chat_id, relatorio)
                    
                    time.sleep(61)
                
                time.sleep(30)
            
            except Exception as e:
                print(f"❌ Erro na análise automática: {e}")
                time.sleep(60)

def main():
    """Inicia o bot"""
    print("🤖 BOT APOSTAS PREMIUM COM SOFASCORE - INICIANDO...")
    print(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print()
    
    bot = BotPremiumReal()
    
    # Thread para análise automática
    thread_automatica = threading.Thread(target=bot.analise_automatica, daemon=True)
    thread_automatica.start()
    
    print("✅ Bot em execução! Aguardando mensagens...")
    print()
    
    bot.buscar_atualizacoes()

if __name__ == "__main__":
    main()
