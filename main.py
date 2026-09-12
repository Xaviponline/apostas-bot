from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot ativado com sucesso!")

app = Application.builder().token("8630778306:AAHyZHgyYyvz93jJCkQ5yiQgXjVOvfptgUg").build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
