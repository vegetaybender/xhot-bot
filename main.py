import io
import logging
import os
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, MODELS, FREE_TEXT_REPLIES, WEBHOOK_URL, PORT
from drive_service import get_random_media, download_file

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def model_keyboard():
    buttons = [
        [InlineKeyboardButton(m["name"], callback_data=f"model:{key}")]
        for key, m in MODELS.items()
    ]
    return InlineKeyboardMarkup(buttons)


def model_menu_keyboard(model_key):
    buttons = [
        [InlineKeyboardButton("📸 Foto", callback_data="action:photo"),
         InlineKeyboardButton("🎬 Video", callback_data="action:video")],
        [InlineKeyboardButton("🎲 Sorpresa", callback_data="action:surprise")],
        [InlineKeyboardButton("🔄 Cambiar modelo", callback_data="action:models"),
         InlineKeyboardButton("🏠 Menú principal", callback_data="action:menu")],
    ]
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("model", None)
    text = "Hola 👋 Bienvenido/a a *Xhot* 🔥\n\nElegí una modelo para chatear:"
    if update.message:
        await update.message.reply_text(text, reply_markup=model_keyboard(), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=model_keyboard(), parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("model:"):
        key = data.split(":", 1)[1]
        if key not in MODELS:
            await query.edit_message_text("Modelo no encontrada.")
            return
        context.user_data["model"] = key
        name = MODELS[key]["name"]
        await query.edit_message_text(
            f"Ahora estás chateando con *{name}* 💬\nPedime una foto o un video 👇",
            reply_markup=model_menu_keyboard(key),
            parse_mode="Markdown",
        )
        return

    if data == "action:models":
        await query.edit_message_text("Elegí una modelo:", reply_markup=model_keyboard())
        context.user_data.pop("model", None)
        return

    if data == "action:menu":
        await query.edit_message_text("Menú principal. Elegí una modelo:", reply_markup=model_keyboard())
        context.user_data.pop("model", None)
        return

    model_key = context.user_data.get("model")
    if not model_key:
        await query.edit_message_text("Primero elegí una modelo 👇", reply_markup=model_keyboard())
        return

    kind = None
    if data == "action:photo":
        kind = "image"
    elif data == "action:video":
        kind = "video"
    elif data == "action:surprise":
        kind = "any"

    if kind is None:
        return

    await query.edit_message_text("Buscando contenido... ⏳")
    try:
        media = get_random_media(model_key, kind)
    except Exception as e:
        logger.exception("Error listando Drive")
        await query.edit_message_text("Hubo un error accediendo a Drive 😕", reply_markup=model_menu_keyboard(model_key))
        return

    if not media:
        await query.edit_message_text("No encontré contenido de ese tipo 😕", reply_markup=model_menu_keyboard(model_key))
        return

    name = MODELS[model_key]["name"]
    caption = f"{name} 🔥"

    try:
        fh = download_file(media["id"])
    except Exception as e:
        logger.exception("Error descargando archivo")
        await query.edit_message_text("No pude descargar el archivo 😕", reply_markup=model_menu_keyboard(model_key))
        return

    mime = media.get("mimeType", "")
    size = int(media.get("size") or 0)
    if size and size > 45 * 1024 * 1024:
        await query.message.reply_text(
            f"El archivo es muy grande para enviarlo por acá ({size//1024//1024}MB). Pedime otro 😊",
            reply_markup=model_menu_keyboard(model_key),
        )
        return

    try:
        if mime.startswith("image/"):
            await query.message.reply_photo(photo=fh, caption=caption)
        elif mime.startswith("video/"):
            await query.message.reply_video(video=fh, caption=caption, supports_streaming=True)
        else:
            await query.message.reply_document(document=fh, filename=media["name"], caption=caption)
    except Exception as e:
        logger.exception("Error enviando a Telegram")
        await query.message.reply_text("No pude enviar el archivo 😕", reply_markup=model_menu_keyboard(model_key))
        return

    await query.message.reply_text("¿Querés otro? 👇", reply_markup=model_menu_keyboard(model_key))


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model_key = context.user_data.get("model")
    if model_key:
        name = MODELS[model_key]["name"]
        reply = random.choice(FREE_TEXT_REPLIES)
        await update.message.reply_text(f"{name}: {reply}", reply_markup=model_menu_keyboard(model_key))
    else:
        await update.message.reply_text("Usá /start para elegir una modelo 👇", reply_markup=model_keyboard())


async def error_handler(update, context):
    logger.exception("Error no manejado", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    if WEBHOOK_URL:
        url_path = BOT_TOKEN
        webhook_url = f"{WEBHOOK_URL}/{url_path}"
        logger.info("Iniciando webhook en %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=url_path,
            webhook_url=webhook_url,
            allowed_updates=["message", "callback_query"],
        )
    else:
        logger.info("Iniciando polling")
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
