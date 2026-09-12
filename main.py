#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BOT APOSTAS INTELIGENTES
Análise automática de apostas desportivas
Telegram: @ultimatsolution
"""

import logging
import json
from datetime import datetime, timedelta
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
from analise import AnalisadorApostas

# Configuração logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuração
TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"
CHAT_ID = None  # Será descoberto automaticamente

class BotApostasInteligentes:
    def __init__(self):
        self.analisador = AnalisadorApostas()
        self.historico = {}
        self.ultima_analise = None
        
    async def enviar_analise_diaria(self, context):
        """Envia análise automática diariamente"""
        try:
            logger.info("Iniciando análise do dia...")
            
            # Busca todos os jogos
            jogos = self.analisador.buscar_todos_jogos()
            logger.info(f"Total de jogos analisados: {len(jogos)}")
            
            # Filtra TOP 3
            top_3 = self.analisador.filtrar_top_apostas(jogos, limite=3)
            logger.info(f"TOP recomendadas: {len(top_3)}")
            
            if top_3:
                # Formata mensagem
                mensagem = self.formatar_analise(top_3)
                
                # Envia para todos os chats
                for chat_id in self.obter_chats_ativos():
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=mensagem,
                            parse_mode='HTML'
                        )
                        logger.info(f"Análise enviada para chat {chat_id}")
                    except Exception as e:
                        logger.error(f"Erro ao enviar para {chat_id}: {e}")
                
                self.ultima_analise = datetime.now()
            else:
                logger.warning("Nenhuma aposta com valor encontrada hoje")
                
        except Exception as e:
            logger.error(f"Erro na análise diária: {e}")
    
    async def rastrear_live(self, context):
        """Rastreia jogos em tempo real"""
        try:
            jogos_vivos = self.analisador.buscar_jogos_vivos()
            
            for jogo in jogos_vivos:
                # Atualiza probabilidades
                analise = self.analisador.atualizar_jogo_vivo(jogo)
                
                if analise['mudanca_importante']:
                    mensagem = self.formatar_update_live(analise)
                    
                    for chat_id in self.obter_chats_ativos():
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=mensagem,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            logger.error(f"Erro ao enviar update: {e}")
        
        except Exception as e:
            logger.error(f"Erro no rastreio live: {e}")
    
    def formatar_analise(self, apostas):
        """Formata análise em HTML para Telegram"""
        mensagem = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        mensagem += "🎯 <b>ANÁLISE PREMIUM</b> - " + datetime.now().strftime("%d/%m/%Y") + "\n"
        mensagem += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, aposta in enumerate(apostas, 1):
            risco_emoji = self.get_risco_emoji(aposta['risco'])
            
            mensagem += f"<b>{self.get_numero_emoji(idx)} #{idx} - {aposta['titulo']}</b>\n\n"
            mensagem += f"⚽ <b>{aposta['jogo']}</b> ({aposta['horario']})\n"
            mensagem += f"🏆 {aposta['liga']}\n\n"
            
            mensagem += f"💰 <b>APOSTA PRINCIPAL:</b>\n"
            mensagem += f"<code>{aposta['tipo']} @{aposta['odds']}</code>\n"
            mensagem += f"Casa: {aposta['casa']}\n\n"
            
            mensagem += f"📈 <b>ANÁLISE:</b>\n"
            mensagem += f"Probabilidade: <b>{aposta['probabilidade']}%</b> {'⭐' * aposta['confianca']}\n"
            mensagem += f"ROI: <b>+{aposta['roi']}%</b>\n"
            mensagem += f"Risco: {risco_emoji} {aposta['risco']}\n\n"
            
            mensagem += f"💡 <b>POR QUÊ:</b>\n"
            mensagem += f"{aposta['explicacao']}\n\n"
            
            mensagem += f"💰 <b>GANHO ESPERADO:</b>\n"
            mensagem += f"€5 → €{aposta['ganho_5']} (+€{aposta['ganho_5']-5})\n"
            mensagem += f"€10 → €{aposta['ganho_10']} (+€{aposta['ganho_10']-10})\n\n"
            
            if aposta['multipla']:
                mensagem += f"🚀 <b>MÚLTIPLA SUGERIDA:</b>\n"
                mensagem += f"<code>{aposta['multipla']['descricao']}</code>\n"
                mensagem += f"Odds: {aposta['multipla']['odds']} | Prob: {aposta['multipla']['prob']}%\n"
                mensagem += f"€5 → €{aposta['multipla']['ganho']} (ROI +{aposta['multipla']['roi']}%)\n"
                mensagem += f"Risco: {self.get_risco_emoji(aposta['multipla']['risco'])} {aposta['multipla']['risco']}\n\n"
            
            mensagem += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Estratégia final
        mensagem += "<b>🎯 ESTRATÉGIA RECOMENDADA:</b>\n\n"
        mensagem += "Conservador: €5+€5+€5 (simples)\n"
        mensagem += "Equilibrado: €6 Dupla + €6 Simples\n"
        mensagem += "Agressivo: €5 Tripla + €5 Dupla\n\n"
        
        mensagem += "[Abrir Betclic] [Abrir Betano]\n\n"
        mensagem += "💬 Comentem: ✅ Se vão apostar"
        
        return mensagem
    
    def formatar_update_live(self, analise):
        """Formata update de jogo ao vivo"""
        mensagem = f"⚽ <b>{analise['jogo']}</b>\n"
        mensagem += f"🔴 Placar: {analise['placar']} (Min {analise['minuto']})\n\n"
        mensagem += f"📈 {analise['tipo']}: {analise['probabilidade']}%\n"
        
        if analise['mudanca_significativa']:
            mensagem += "⭐⭐⭐⭐ <b>VALOR MELHOROU!</b>\n"
        
        return mensagem
    
    @staticmethod
    def get_numero_emoji(num):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        return emojis[num-1] if num <= 5 else "🔹"
    
    @staticmethod
    def get_risco_emoji(risco):
        riscos = {
            "BAIXO": "🟢",
            "MÉDIO": "🟡",
            "MÉDIO-ALTO": "🟠",
            "ALTO": "🔴"
        }
        return riscos.get(risco, "⚪")
    
    def obter_chats_ativos(self):
        """Obtém lista de chats para enviar mensagens"""
        # Pode armazenar em ficheiro ou BD
        if CHAT_ID:
            return [CHAT_ID]
        return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    global CHAT_ID
    CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text(
        "🎯 <b>BOT APOSTAS INTELIGENTES</b>\n\n"
        "✅ Bot ativado com sucesso!\n"
        "📊 Análise automática em funcionamento\n"
        "🔔 Receberás recomendações diárias\n\n"
        "Próxima análise: 08:00 (manhã)",
        parse_mode='HTML'
    )
    
    logger.info(f"Bot iniciado no chat: {CHAT_ID}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status"""
    bot = context.bot_data.get('bot_apostas')
    
    texto = "📊 <b>STATUS BOT</b>\n\n"
    texto += "✅ Bot ativo\n"
    texto += "📈 Análise automática funcionando\n"
    
    if bot.ultima_analise:
        texto += f"⏰ Última análise: {bot.ultima_analise.strftime('%H:%M:%S')}\n"
    
    texto += "\nLigas monitoradas:\n"
    texto += "🏴 Premier League\n"
    texto += "🇪🇸 La Liga\n"
    texto += "🇮🇹 Serie A\n"
    texto += "🇩🇪 Bundesliga\n"
    texto += "🇫🇷 Ligue 1\n"
    texto += "🇵🇹 Portugal\n"
    texto += "🇧🇷 Brasileirão\n"
    texto += "🇺🇸 MLS\n"
    texto += "🇸🇦 SPL (Cristiano Ronaldo)\n"
    
    await update.message.reply_text(texto, parse_mode='HTML')


async def analisa_agora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /analisa (força análise manual)"""
    bot = context.bot_data.get('bot_apostas')
    
    await update.message.reply_text("🔄 Analisando jogos... aguarda...")
    
    try:
        jogos = bot.analisador.buscar_todos_jogos()
        top_3 = bot.analisador.filtrar_top_apostas(jogos, limite=3)
        
        mensagem = bot.formatar_analise(top_3)
        await update.message.reply_text(mensagem, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erro: {e}")


def main():
    """Função principal"""
    logger.info("Iniciando BOT APOSTAS INTELIGENTES...")
    
    # Cria aplicação
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Cria instância do bot
    bot_apostas = BotApostasInteligentes()
    app.bot_data['bot_apostas'] = bot_apostas
    
    # Adiciona handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("analisa", analisa_agora))
    
    # Jobs (tarefas agendadas)
    job_queue = app.job_queue
    
    # Análise diária às 08:00
    job_queue.run_daily(
        bot_apostas.enviar_analise_diaria,
        time=datetime.now().replace(hour=8, minute=0, second=0)
    )
    
    # Rastreio live a cada minuto (durante jogos)
    job_queue.run_repeating(
        bot_apostas.rastrear_live,
        interval=60
    )
    
    logger.info("Bot iniciado com sucesso! ✅")
    logger.info("Análise diária agendada para 08:00")
    logger.info("Rastreio live ativo")
    
    # Inicia polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
