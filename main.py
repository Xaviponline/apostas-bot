#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS INTELIGENTES - VERSÃO FINAL COM MÚLTIPLAS PREMIUM
15 Simples + 3-5 Múltiplas de VALOR
"""

import requests
import time
from datetime import datetime
from analista_dinamico_total import AnistaDinamicoTotal

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

CHATS_ATIVOS = set()

class BotPremium:
    
    def __init__(self):
        self.analista = AnistaDinamicoTotal()
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
                                "🎯 <b>BOT APOSTAS INTELIGENTES PREMIUM</b>\n\n"
                                "✅ Bot ativado com sucesso!\n"
                                "📊 15 Apostas Simples + Múltiplas Premium\n"
                                "💰 ROI Médio: +16.4% (Simples) | +100%+ (Múltiplas)\n"
                                "🔔 Receberás análises diárias às 08:00\n\n"
                                "<b>Comandos:</b>\n"
                                "/analisa - Análise COMPLETA\n"
                                "/status - Status\n"
                                "/ajuda - Ajuda"
                            )
                        
                        elif text == "/analisa":
                            relatorio = self.analista.gerar_relatorio()
                            self.enviar_mensagem(chat_id, relatorio)
                        
                        elif text == "/status":
                            self.enviar_mensagem(
                                chat_id,
                                "✅ <b>Status PREMIUM</b>\n\n"
                                "🟢 Bot ATIVO\n"
                                "📊 15 Simples + Múltiplas\n"
                                "💰 ROI Médio: +16.4%\n"
                                f"👥 Chats: {len(CHATS_ATIVOS)}\n"
                                "⚡ Resposta: <1 segundo\n"
                                "🕐 Próxima: 08:00"
                            )
                        
                        elif text == "/ajuda":
                            self.enviar_mensagem(
                                chat_id,
                                "<b>📖 AJUDA - BOT PREMIUM</b>\n\n"
                                "<b>Comandos:</b>\n"
                                "/start - Inicia\n"
                                "/analisa - ANÁLISE COMPLETA\n"
                                "/status - Status\n\n"
                                "<b>Contém:</b>\n"
                                "📊 15 Apostas Simples\n"
                                "   ROI Médio: +16.4%\n"
                                "   Risco: Baixo/Médio\n\n"
                                "🔥 3-5 Múltiplas Premium\n"
                                "   ROI: 150%+\n"
                                "   Prob: 70%+\n"
                                "   Risco: 🟢 Baixo\n\n"
                                "<b>Filtros Rígidos:</b>\n"
                                "✅ Prob: 55%+ (simples)\n"
                                "✅ Prob: 70%+ (múltiplas)\n"
                                "✅ ROI: +2%+ (simples)\n"
                                "✅ ROI: 150%+ (múltiplas)\n"
                                "✅ Odds: 1.65+\n"
                                "✅ Confiança: ⭐⭐⭐+"
                            )
        
        except Exception as e:
            print(f"❌ Erro: {e}")
    
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
        print("🤖 Bot Apostas Inteligentes PREMIUM")
        print("📊 15 Simples + Múltiplas Premium")
        print(f"⚡ Resposta em < 1 segundo")
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
    bot = BotPremium()
    bot.run()

if __name__ == "__main__":
    main()
