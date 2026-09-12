from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_TOKEN = "8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 BOT APOSTAS INTELIGENTES\n\n"
        "✅ Bot ativado com sucesso!\n"
        "📊 Análise automática em funcionamento\n"
        "🔔 Receberás recomendações diárias"
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
