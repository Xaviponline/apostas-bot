#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS INTELIGENTES - COM APIs REAIS
SofaScore + OddsAPI
"""

import requests
import time
from datetime import datetime
from analista_api import AnalistaAPI

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
ODDS_API_KEY = "6d8b199647b759a1a5380376780807ad"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CHATS_ATIVOS = set()

class BotApostasAPI:
    
    def __init__(self):
        self.analista = AnalistaAPI(ODDS_API_KEY)
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
            print(f"✅ Mensagem enviada para {chat_id}")
        except Exception as e:
            print(f"❌ Erro ao enviar: {e}")
    
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
                        
                        CHATS_ATIVOS.add(chat_id)
                        
                        if text == "/start":
                            self.enviar_mensagem(
                                chat_id,
                                "🎯 <b>BOT APOSTAS INTELIGENTES</b>\n\n"
                                "✅ Bot com APIs REAIS ativado!\n"
                                "📊 Análise de SofaScore + OddsAPI\n"
                                "🔔 Receberás análises diárias às 08:00\n\n"
                                "<b>Comandos:</b>\n"
                                "/analisa - Análise do dia agora\n"
                                "/status - Status do bot\n"
                                "/ajuda - Ajuda"
                            )
                        
                        elif text == "/analisa":
                            self.enviar_mensagem(chat_id, "⏳ Analisando jogos (pode demorar)...")
                            relatorio = self.analista.gerar_relatorio()
                            self.enviar_mensagem(chat_id, relatorio)
                        
                        elif text == "/status":
                            self.enviar_mensagem(
                                chat_id,
                                "✅ <b>Status do Bot</b>\n\n"
                                "🟢 Bot ATIVO\n"
                                "📊 Análise com APIs REAIS\n"
                                "🔌 SofaScore + OddsAPI integrados\n"
                                f"👥 Chats ativos: {len(CHATS_ATIVOS)}\n"
                                "🕐 Próxima análise: 08:00"
                            )
                        
                        elif text == "/ajuda":
                            self.enviar_mensagem(
                                chat_id,
                                "<b>📖 AJUDA</b>\n\n"
                                "<b>Comandos:</b>\n"
                                "/start - Inicia bot\n"
                                "/analisa - Análise manual\n"
                                "/status - Ver status\n"
                                "/ajuda - Esta mensagem\n\n"
                                "<b>Filtros Rígidos:</b>\n"
                                "✅ Probabilidade: 55%+\n"
                                "✅ ROI: +2%+\n"
                                "✅ Confiança: ⭐⭐⭐+\n"
                                "✅ Odds: 1.65+"
                            )
        
        except Exception as e:
            print(f"❌ Erro ao processar updates: {e}")
    
    def verificar_hora_analise(self):
        """Verifica se é hora de enviar análise (08:00)"""
        hora_agora = datetime.now()
        
        if self.ultima_analise is None or \
           self.ultima_analise.date() != hora_agora.date():
            
            if hora_agora.hour == 8 and hora_agora.minute < 5:
                return True
        
        return False
    
    def enviar_analise_diaria(self):
        """Envia análise diária para todos os chats"""
        
        if not CHATS_ATIVOS:
            print("❌ Nenhum chat ativo")
            return
        
        print("📊 Enviando análise diária...")
        relatorio = self.analista.gerar_relatorio()
        
        for chat_id in CHATS_ATIVOS:
            self.enviar_mensagem(chat_id, relatorio)
        
        self.ultima_analise = datetime.now()
    
    def run(self):
        """Loop principal"""
        print("🤖 Bot Apostas Inteligentes (APIs REAIS) iniciado!")
        print(f"📊 SofaScore + OddsAPI integrados")
        print(f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}")
        
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
    bot = BotApostasAPI()
    bot.run()

if __name__ == "__main__":
    main()
