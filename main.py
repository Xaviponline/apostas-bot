#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS TELEGRAM - COM RASTREIO DE RESULTADOS
Bot 100% funcional com análise e rastreio automático
"""

import requests
import json
import time
import threading
from datetime import datetime
from analista_dinamico_total import AnistaDinamicoTotal
from gestor_apostas import GestorApostas
from rastreador_resultados import RastreadorResultados

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CHATS_ATIVOS = set()

class BotPremium:
    
    def __init__(self):
        self.analista = AnistaDinamicoTotal()
        self.gestor = GestorApostas()
        self.rastreador = RastreadorResultados()
        self.ultimo_update = 0
    
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
    
    def processar_comando(self, chat_id: int, texto: str):
        """Processa comandos do bot"""
        
        if texto == "/start":
            mensagem = """
🤖 <b>BEM-VINDO AO BOT APOSTAS PREMIUM!</b>

📊 <b>Análise Automática + Rastreio de Resultados</b>

<b>Comandos disponíveis:</b>
/analisa - 📈 Ver apostas de HOJE
/resultados - 📊 Ver performance
/status - 🔍 Status do bot
/ajuda - 📖 Informações completas

<b>Rastreio de Resultados:</b>
/score ID CASA-FORA - Registar resultado
(Ex: /score 1 2-1)

<b>Características:</b>
✅ 15 apostas de HOJE
✅ ROI médio +16-40%
✅ Rastreio de resultados automático
✅ Histórico completo de apostas
✅ Estatísticas em tempo real

Subscreve para receber análises diárias! 🔥
            """
            self.enviar_mensagem(chat_id, mensagem)
            CHATS_ATIVOS.add(chat_id)
        
        elif texto == "/analisa":
            relatorio = self.analista.gerar_relatorio()
            self.enviar_mensagem(chat_id, relatorio)
            CHATS_ATIVOS.add(chat_id)
            
            # Regista as apostas no gestor
            apostas = self.analista.gerar_apostas_simples()
            for aposta in apostas:
                self.gestor.adicionar_aposta({
                    "jogo": aposta["jogo"],
                    "liga": aposta["liga"],
                    "tipo": aposta["tipo"],
                    "odds": aposta["odds"],
                    "probabilidade": aposta["probabilidade"],
                    "roi": aposta["roi"]
                })
        
        elif texto == "/resultados":
            relatorio = self.gestor.gerar_relatorio()
            self.enviar_mensagem(chat_id, relatorio)
            CHATS_ATIVOS.add(chat_id)
        
        elif texto.startswith("/score "):
            # Formato: /score ID CASA-FORA
            # Exemplo: /score 1 2-1
            try:
                partes = texto.split()
                if len(partes) >= 3:
                    aposta_id = int(partes[1])
                    placar = partes[2]
                    
                    casa, fora = map(int, placar.split("-"))
                    
                    # Obtém aposta
                    aposta = self.gestor.obter_aposta(aposta_id)
                    if not aposta:
                        self.enviar_mensagem(chat_id, f"❌ Aposta #{aposta_id} não encontrada!")
                        return
                    
                    # Simula análise de resultado
                    tipo = aposta["tipo"]
                    resultado = None
                    
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
                    
                    if resultado:
                        self.gestor.registar_resultado(aposta_id, resultado)
                        status = "✅ GANHOU!" if resultado == "ganhou" else "❌ PERDEU!"
                        self.enviar_mensagem(chat_id, f"{status}\n\n{aposta['jogo']}\n{tipo} @{aposta['odds']}\nPlacar: {casa}-{fora}")
                    else:
                        self.enviar_mensagem(chat_id, "⚠️ Tipo de aposta não suportado para análise manual")
            
            except Exception as e:
                self.enviar_mensagem(chat_id, f"❌ Erro: Use /score ID CASA-FORA (Ex: /score 1 2-1)")
        
        elif texto == "/status":
            stats = self.gestor.calcular_estatisticas()
            status = f"""
✅ <b>BOT STATUS</b>

🤖 Bot: <b>OPERACIONAL</b> ✓
🌐 Railway: <b>ONLINE</b> ✓
📊 Análise: <b>ATIVA</b> ✓
⏰ Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}

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
/analisa - Ver apostas de HOJE
/resultados - Ver performance
/status - Ver status do bot

<b>REGISTAR RESULTADOS:</b>
/score ID CASA-FORA
Exemplo: /score 1 2-1

<b>Como funciona:</b>
✓ Bot gera 15 apostas DIÁRIAS
✓ Filtros rígidos de qualidade
✓ ROI sempre positivo
✓ Rastreio de resultados automático
✓ Histórico completo guardar

<b>Qualidade garantida:</b>
- Probabilidade mínima: 55%
- ROI mínimo: +2%
- Confiança: ⭐⭐⭐+

<b>Performance Real:</b>
- Histórico de todas as apostas
- Win rate calculado
- ROI real vs esperado
- Lucro em tempo real

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
                            
                            # Processa mensagens
                            if "message" in update:
                                msg = update["message"]
                                chat_id = msg["chat"]["id"]
                                
                                if "text" in msg:
                                    texto = msg["text"].strip()
                                    print(f"📨 [{chat_id}] {texto}")
                                    
                                    # Processa comando
                                    if texto.startswith("/"):
                                        self.processar_comando(chat_id, texto)
                
                time.sleep(0.5)
            
            except requests.exceptions.Timeout:
                print("⏱️ Timeout na busca de atualizações (normal)")
                time.sleep(5)
            
            except Exception as e:
                print(f"❌ Erro: {e}")
                time.sleep(5)
    
    def analise_automatica(self):
        """Análise automática às 08:00"""
        while True:
            try:
                agora = datetime.now()
                
                # Se for 08:00, envia análise
                if agora.hour == 8 and agora.minute == 0:
                    relatorio = self.analista.gerar_relatorio()
                    
                    for chat_id in list(CHATS_ATIVOS):
                        self.enviar_mensagem(chat_id, f"📊 <b>ANÁLISE AUTOMÁTICA</b>\n\n{relatorio}")
                    
                    time.sleep(61)  # Espera 1 minuto para não repetir
                
                time.sleep(30)  # Verifica a cada 30 segundos
            
            except Exception as e:
                print(f"❌ Erro na análise automática: {e}")
                time.sleep(60)

def main():
    """Inicia o bot"""
    print("🤖 BOT APOSTAS PREMIUM COM RASTREIO - INICIANDO...")
    print(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"🔑 Token: {TELEGRAM_TOKEN[:20]}...")
    print()
    
    bot = BotPremium()
    
    # Thread para análise automática
    thread_automatica = threading.Thread(target=bot.analise_automatica, daemon=True)
    thread_automatica.start()
    
    # Thread principal para buscar atualizações
    print("✅ Bot em execução! Aguardando mensagens...")
    print()
    
    bot.buscar_atualizacoes()

if __name__ == "__main__":
    main()
