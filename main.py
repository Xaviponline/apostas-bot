#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS INTELIGENTES - VERSÃO COMPLETA
Análise profissional + notificações automáticas
"""

import requests
import time
from datetime import datetime
from analista import AnalistaApostas

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Armazena chats ativos
CHATS_ATIVOS = set()

class BotApostas:
    
    def __init__(self):
        self.analista = AnalistaApostas()
        self.ultima_analise = None
        self.offset = 0
    
    def enviar_mensagem(self, chat_id, texto):
        """Envia mensagem para Telegram"""
        url = f"{BASE_URL}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML"
        }
        try:
            requests.post(url, data=data, timeout=10)
            print(f"Mensagem enviada para {chat_id}")
        except Exception as e:
            print(f"Erro ao enviar: {e}")
    
    def processar_updates(self):
        """Processa mensagens recebidas"""
        url = f"{BASE_URL}/getUpdates"
        params = {"offset": self.offset, "timeout": 10}
        
        try:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()
            
            if "result" in data:
                for update in data["result"]:
                    self.offset = update["update_id"] + 1
                    
                    if "message" in update:
                        message = update["message"]
                        chat_id = message["chat"]["id"]
                        text = message.get("text", "")
                        
                        # Registra chat ativo
                        CHATS_ATIVOS.add(chat_id)
                        
                        # Processa comando
                        if text == "/start":
                            self.enviar_mensagem(
                                chat_id,
                                "🎯 <b>BOT APOSTAS INTELIGENTES</b>\n\n"
                                "✅ Bot ativado com sucesso!\n"
                                "📊 Análise automática funcionando\n"
                                "🔔 Receberás análises diárias às 08:00\n\n"
                                "<b>Comandos:</b>\n"
                                "/analisa - Análise do dia agora\n"
                                "/status - Status do bot"
                            )
                        
                        elif text == "/analisa":
                            relatorio = self.analista.gerar_relatorio()
                            self.enviar_mensagem(chat_id, relatorio)
                        
                        elif text == "/status":
                            self.enviar_mensagem(
                                chat_id,
                                "✅ Bot ativo\n"
                                "📊 Análise automática funcionando\n"
                                f"👥 Chats ativos: {len(CHATS_ATIVOS)}"
                            )
        
        except Exception as e:
            print(f"Erro ao processar updates: {e}")
    
    def verificar_hora_analise(self):
        """Verifica se é hora de enviar análise (08:00)"""
        hora_agora = datetime.now()
        
        # Se passou a última análise
        if self.ultima_analise is None or \
           self.ultima_analise.date() != hora_agora.date():
            
            # Se é 08:00 (entre 08:00 e 08:05)
            if hora_agora.hour == 8 and hora_agora.minute < 5:
                return True
        
        return False
    
    def enviar_analise_diaria(self):
        """Envia análise diária para todos os chats ativos"""
        
        if not CHATS_ATIVOS:
            print("Nenhum chat ativo")
            return
        
        print("Enviando análise diária...")
        relatorio = self.analista.gerar_relatorio()
        
        for chat_id in CHATS_ATIVOS:
            self.enviar_mensagem(chat_id, relatorio)
        
        self.ultima_analise = datetime.now()
    
    def run(self):
        """Loop principal do bot"""
        print("🤖 Bot Apostas Inteligentes iniciado!")
        print(f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}")
        
        contador = 0
        
        while True:
            try:
                # Processa mensagens recebidas
                self.processar_updates()
                
                # Verifica hora de análise diária
                if self.verificar_hora_analise():
                    self.enviar_analise_diaria()
                
                # A cada 10 iterações, verifica e envia status
                contador += 1
                if contador % 60 == 0:  # A cada ~60 segundos
                    print(f"✅ Bot ativo - {datetime.now().strftime('%H:%M:%S')} - Chats: {len(CHATS_ATIVOS)}")
                
                time.sleep(1)
            
            except KeyboardInterrupt:
                print("\n⏹️ Bot parado")
                break
            except Exception as e:
                print(f"❌ Erro: {e}")
                time.sleep(5)

def main():
    bot = BotApostas()
    bot.run()

if __name__ == "__main__":
    main()
