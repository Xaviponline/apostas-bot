#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS INTELIGENTES - VERSÃO FINAL ROBUSTA
Com tratamento de erros e fallback
"""

import requests
import time
from datetime import datetime
from analista_robusto import AnalistaRobusto

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
ODDS_API_KEY = "6d8b199647b759a1a5380376780807ad"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CHATS_ATIVOS = set()

class BotFinal:
    
    def __init__(self):
        self.analista = AnalistaRobusto(ODDS_API_KEY)
        self.ultima_analise = None
        self.offset = 0
    
    def enviar_mensagem(self, chat_id, texto):
        """Envia mensagem"""
        url = f"{BASE_URL}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "HTML"
        }
        try:
            requests.post(url, data=data, timeout=10)
            print(f"✅ Mensagem para {chat_id}")
        except Exception as e:
            print(f"❌ Erro: {e}")
    
    def processar_updates(self):
        """Processa mensagens"""
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
                        
                        CHATS_ATIVOS.add(chat_id)
                        
                        if text == "/start":
                            self.enviar_mensagem(
                                chat_id,
                                "🎯 <b>BOT APOSTAS INTELIGENTES</b>\n\n"
                                "✅ Bot ativado com sucesso!\n"
                                "📊 Análise com APIs + Fallback\n"
                                "🔔 Receberás análises diárias às 08:00\n\n"
                                "<b>Comandos:</b>\n"
                                "/analisa - Análise do dia agora\n"
                                "/status - Status\n"
                                "/ajuda - Ajuda"
                            )
                        
                        elif text == "/analisa":
                            self.enviar_mensagem(chat_id, "⏳ Analisando jogos...")
                            relatorio = self.analista.gerar_relatorio()
                            self.enviar_mensagem(chat_id, relatorio)
                        
                        elif text == "/status":
                            self.enviar_mensagem(
                                chat_id,
                                "✅ <b>Status</b>\n\n"
                                "🟢 Bot ATIVO\n"
                                "📊 Análise com APIs\n"
                                f"👥 Chats: {len(CHATS_ATIVOS)}\n"
                                "🕐 Próxima: 08:00"
                            )
                        
                        elif text == "/ajuda":
                            self.enviar_mensagem(
                                chat_id,
                                "<b>📖 AJUDA</b>\n\n"
                                "/start - Inicia\n"
                                "/analisa - Análise manual\n"
                                "/status - Status\n\n"
                                "<b>Filtros:</b>\n"
                                "✅ Prob: 55%+\n"
                                "✅ ROI: +2%+\n"
                                "✅ Conf: ⭐⭐⭐+\n"
                                "✅ Odds: 1.65+"
                            )
        
        except Exception as e:
            print(f"❌ Erro updates: {e}")
    
    def verificar_hora_analise(self):
        """Verifica hora"""
        hora_agora = datetime.now()
        
        if self.ultima_analise is None or \
           self.ultima_analise.date() != hora_agora.date():
            
            if hora_agora.hour == 8 and hora_agora.minute < 5:
                return True
        
        return False
    
    def enviar_analise_diaria(self):
        """Envia análise"""
        
        if not CHATS_ATIVOS:
            return
        
        print("📊 Enviando análise diária...")
        relatorio = self.analista.gerar_relatorio()
        
        for chat_id in CHATS_ATIVOS:
            self.enviar_mensagem(chat_id, relatorio)
        
        self.ultima_analise = datetime.now()
    
    def run(self):
        """Loop principal"""
        print("🤖 Bot Apostas Inteligentes - VERSÃO ROBUSTA")
        print(f"🕐 {datetime.now().strftime('%H:%M:%S')}\n")
        
        contador = 0
        
        while True:
            try:
                self.processar_updates()
                
                if self.verificar_hora_analise():
                    self.enviar_analise_diaria()
                
                contador += 1
                if contador % 60 == 0:
                    print(f"✅ {datetime.now().strftime('%H:%M:%S')} - Chats: {len(CHATS_ATIVOS)}")
                
                time.sleep(1)
            
            except KeyboardInterrupt:
                print("\n⏹️ Bot parado")
                break
            except Exception as e:
                print(f"❌ Erro: {e}")
                time.sleep(5)

def main():
    bot = BotFinal()
    bot.run()

if __name__ == "__main__":
    main()
