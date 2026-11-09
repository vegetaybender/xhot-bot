import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# ====================== CONFIGURACIÓN ======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DRIVE_FOLDER_ID = "1zpDaUJvluGwE8n5YboC2bxViieWaLn9F"  # ID de tu carpeta "yus"

# Nombres de las carpetas de cada modelo (tienen que coincidir exactamente)
MODELOS = {
    "yus": "Yus Lopez",
    "angie": "Angie Watters",
    "valen": "Valen Borelli"
}

# ===========================================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado de cada usuario
user_data = {}

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json",
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)

def get_random_file(folder_name):
    service = get_drive_service()
    
    # Buscar la carpeta de la modelo
    query = f"'{DRIVE_FOLDER_ID}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get("files", [])
    
    if not folders:
        return None
    
    folder_id = folders[0]["id"]
    
    # Buscar archivos dentro de esa carpeta
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    files = results.get("files", [])
    
    if not files:
        return None
    
    return random.choice(files)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Yus López ", callback_data="modelo_yus")],
        [InlineKeyboardButton("Angie Watters ", callback_data="modelo_angie")],
        [InlineKeyboardButton("Valen Borelli ", callback_data="modelo_valen")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔥 *Bienvenido a Xhot*\n\nElegí la modelo con la que querés hablar:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("modelo_"):
        modelo_key = data.split("_")[1]
        modelo_nombre = MODELOS[modelo_key]
        
        user_data[user_id] = {"modelo": modelo_key, "nombre": modelo_nombre}
        
        keyboard = [
            [InlineKeyboardButton("Foto ", callback_data="foto")],
            [InlineKeyboardButton("Video ", callback_data="video")],
            [InlineKeyboardButton("Cambiar de modelo", callback_data="cambiar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Ahora estás hablando con *{modelo_nombre}*\n\n¿Qué querés hacer?",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif data == "foto" or data == "video":
        if user_id not in user_data:
            await query.edit_message_text("Primero elegí una modelo con /start")
            return
        
        modelo_key = user_data[user_id]["modelo"]
        carpeta = MODELOS[modelo_key]
        
        await query.edit_message_text("Buscando archivo... ")
        
        archivo = get_random_file(carpeta)
        
        if not archivo:
            await query.message.reply_text("No encontré archivos en esta carpeta ")
            return
        
        # Descargar y enviar
        service = get_drive_service()
        request = service.files().get_media(fileId=archivo["id"])
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        file_data.seek(0)
        
        if "video" in archivo["mimeType"] or data == "video":
            await query.message.reply_video(video=file_data, filename=archivo["name"])
        else:
            await query.message.reply_photo(photo=file_data, filename=archivo["name"])
        
        # Volver a mostrar los botones
        keyboard = [
            [InlineKeyboardButton("Foto ", callback_data="foto")],
            [InlineKeyboardButton("Video ", callback_data="video")],
            [InlineKeyboardButton("Cambiar de modelo", callback_data="cambiar")]
        ]
        await query.message.reply_text("¿Qué más querés?", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "cambiar":
        keyboard = [
            [InlineKeyboardButton("Yus López ", callback_data="modelo_yus")],
            [InlineKeyboardButton("Angie Watters ", callback_data="modelo_angie")],
            [InlineKeyboardButton("Valen Borelli ", callback_data="modelo_valen")]
        ]
        await query.edit_message_text(
            "Elegí otra modelo:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    texto = update.message.text
    
    if user_id not in user_data:
        await update.message.reply_text("Primero elegí una modelo con /start")
        return
    
    nombre = user_data[user_id]["nombre"]
    await update.message.reply_text(f"*{nombre}* está escribiendo...\n\n_(Modo semi-automático activado)_", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot Xhot iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()