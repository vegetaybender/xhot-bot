import io
import logging
import os
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, MODELS, FREE_TEXT_REPLIES, WEBHOOK_URL, PORT
from drive_service import get_random_media, get_random_album, download_file
import chat_ai as grok_chat

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
         InlineKeyboardButton("🖼 Álbum (3)", callback_data="action:album")],
        [InlineKeyboardButton("🎬 Video", callback_data="action:video"),
         InlineKeyboardButton("🎲 Sorpresa", callback_data="action:surprise")],
        [InlineKeyboardButton("🔄 Cambiar modelo", callback_data="action:models"),
         InlineKeyboardButton("🏠 Menú principal", callback_data="action:menu")],
    ]
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("model", None)
    if update.effective_user:
        grok_chat.reset(update.effective_user.id)
    text = (
        "Hola 👋 Bienvenido/a a *Xhot* 🔥\n\n"
        "Elegí una modelo para chatear:\n\n"
        "Después podés cambiar su rol con /rol (novia, amante, vip) y el nivel de explicitud con /nivel."
    )
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
        if update.effective_user:
            grok_chat.reset(update.effective_user.id)
        name = MODELS[key]["name"]
        role = grok_chat.get_role(update.effective_user.id, key) if update.effective_user else "novia"
        level = grok_chat.get_level(update.effective_user.id) if update.effective_user else "medio"
        await query.edit_message_text(
            f"Ahora estás chateando con *{name}* 💬\n"
            f"Rol: *{role}* · Nivel: *{level}*\n"
            "Cambiá el rol con /rol y el nivel con /nivel\n"
            "Pedime una foto o un video 👇",
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

    if data == "action:album":
        await query.edit_message_text("Preparando álbum... ⏳")
        try:
            images = get_random_album(model_key, 3)
        except Exception as e:
            logger.exception("Error listando Drive")
            await query.edit_message_text("Hubo un error accediendo a Drive 😕", reply_markup=model_menu_keyboard(model_key))
            return
        if not images:
            await query.edit_message_text("No encontré fotos 😕", reply_markup=model_menu_keyboard(model_key))
            return
        media_list = []
        for img in images:
            try:
                fh = download_file(img["id"])
            except Exception as e:
                logger.exception("Error descargando archivo")
                await query.message.reply_text("No pude descargar una foto 😕", reply_markup=model_menu_keyboard(model_key))
                continue
            media_list.append(InputMediaPhoto(media=fh))
        if not media_list:
            await query.edit_message_text("No pude preparar el álbum 😕", reply_markup=model_menu_keyboard(model_key))
            return
        try:
            await query.message.reply_media_group(media=media_list)
        except Exception as e:
            logger.exception("Error enviando álbum")
            await query.message.reply_text("No pude enviar el álbum 😕", reply_markup=model_menu_keyboard(model_key))
            return
        if update.effective_user:
            for img in images:
                grok_chat.note_media(update.effective_user.id, model_key, img.get("name", ""))
            chat_reply = None
            if grok_chat.is_enabled():
                chat_reply = grok_chat.chat(update.effective_user.id, model_key, "Acabo de enviarle un álbum de fotos al usuario. Reacciona brevemente en personaje, como una chica hot mandándole contenido a su cliente/novio, y luego invítalo a pedir otra, todo en un solo mensaje coqueto y sugestivo.")
            if not chat_reply:
                chat_reply = random.choice([
                    "¿Te gustó el álbum? 😏 ¿Querés que te muestre otra cosita? 😉",
                    "Mmm... ¿qué te parece? 😉 ¿Te animás a pedirme otra? 😘",
                    "Espero que te haya gustado 🔥 ¿Querés ver más de mí? 🔥",
                ])
            await query.message.reply_text(chat_reply, reply_markup=model_menu_keyboard(model_key))
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

    mime = media.get("mimeType", "")

    if mime.startswith("video/"):
        await query.edit_message_text("Descargando video... ⏳")
    try:
        fh = download_file(media["id"])
    except Exception as e:
        logger.exception("Error descargando archivo")
        await query.edit_message_text("No pude descargar el archivo 😕", reply_markup=model_menu_keyboard(model_key))
        return

    size = int(media.get("size") or 0)
    if size and size > 45 * 1024 * 1024:
        await query.message.reply_text(
            f"El archivo es muy grande para enviarlo por acá ({size//1024//1024}MB). Pedime otro 😊",
            reply_markup=model_menu_keyboard(model_key),
        )
        return

    try:
        if mime.startswith("image/"):
            await query.message.reply_photo(photo=fh)
        elif mime.startswith("video/"):
            await query.message.reply_video(video=fh, supports_streaming=True)
        else:
            await query.message.reply_document(document=fh, filename=media["name"])
    except Exception as e:
        logger.exception("Error enviando a Telegram")
        await query.message.reply_text("No pude enviar el archivo 😕", reply_markup=model_menu_keyboard(model_key))
        return

    if update.effective_user and media.get("name"):
        grok_chat.note_media(update.effective_user.id, model_key, media["name"])
        chat_reply = None
        if grok_chat.is_enabled():
            chat_reply = grok_chat.chat(update.effective_user.id, model_key, "Acabo de enviarle una foto/video al usuario. Reacciona brevemente en personaje, como una chica hot mandándole contenido a su cliente/novio, y luego invítalo a pedir otra, todo en un solo mensaje coqueto y sugestivo.")
        if not chat_reply:
            chat_reply = random.choice([
                "¿Te gustó? 😏 ¿Querés que te muestre otra cosita? 😉",
                "Mmm... ¿qué te parece? 😉 ¿Te animás a pedirme otra? 😘",
                "Espero que te haya gustado 🔥 ¿Querés ver más de mí? 🔥",
            ])
        await query.message.reply_text(chat_reply, reply_markup=model_menu_keyboard(model_key))

async def roles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    lines = ["*Roles actuales:*"]
    for key, m in MODELS.items():
        role = grok_chat.get_role(user.id, key)
        extra = " + personalidad extra" if grok_chat.get_custom_persona(user.id, key) else ""
        lines.append(f"• {m['name']}: *{role}*{extra}")
    lines.append("")
    lines.append("Cambiar la modelo actual: `/rol novia`, `/rol amante` o `/rol vip`.")
    lines.append("Cambiar una puntual: `/rol yus amante`.")
    lines.append("Personalidad libre: `/persona <texto>` · borrar: `/persona reset`.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    args = context.args or []
    current = context.user_data.get("model")

    if not args:
        if current:
            role = grok_chat.get_role(user.id, current)
            await update.message.reply_text(
                f"*{MODELS[current]['name']}* tiene el rol *{role}*.\n\n"
                "Opciones: novia, amante, vip.\n"
                "Ejemplo: `/rol amante` o `/rol yus novia`.",
                parse_mode="Markdown",
            )
        else:
            await roles_command(update, context)
        return

    role = args[-1].lower()
    if role not in grok_chat.role_names():
        await update.message.reply_text("Rol inválido. Opciones: novia, amante, vip.")
        return

    target = current
    if len(args) >= 2:
        candidate = args[0].lower()
        target = None
        for key, m in MODELS.items():
            if candidate == key or candidate in m["name"].lower():
                target = key
                break
        if not target:
            await update.message.reply_text("No encontré esa modelo. Usá: yus, angie o valen.")
            return

    if not target:
        await update.message.reply_text(
            "Primero elegí una modelo con /start, o indicá: `/rol yus amante`.",
            parse_mode="Markdown",
        )
        return

    grok_chat.set_role(user.id, target, role)
    await update.message.reply_text(
        f"Listo 😉 *{MODELS[target]['name']}* ahora es *{role}*.\n"
        "Reinicié el chat para que tome el nuevo rol.",
        parse_mode="Markdown",
    )


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    model_key = context.user_data.get("model")
    text = " ".join(context.args or []).strip()

    if not model_key:
        await update.message.reply_text("Primero elegí una modelo con /start.")
        return

    name = MODELS[model_key]["name"]
    if not text:
        current = grok_chat.get_custom_persona(user.id, model_key)
        if current:
            await update.message.reply_text(
                f"Personalidad extra de {name}:\n\n{current}\n\nPara borrarla: /persona reset"
            )
        else:
            await update.message.reply_text(
                f"{name} no tiene personalidad extra.\n"
                "Escribí: /persona <texto>\n"
                "Ejemplo: /persona sos una modelo que ama el riesgo y los mensajes a medianoche."
            )
        return

    if text.lower() in ("reset", "borrar", "limpiar"):
        grok_chat.clear_custom_persona(user.id, model_key)
        await update.message.reply_text(f"Listo, borré la personalidad extra de {name}.")
        return

    grok_chat.set_custom_persona(user.id, model_key, text)
    await update.message.reply_text(f"Listo, guardé esa personalidad para {name}. Reinicié el chat.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    model_key = context.user_data.get("model")
    if model_key:
        grok_chat.reset(user.id, model_key)
        await update.message.reply_text(f"Chat con {MODELS[model_key]['name']} reiniciado.")
    else:
        grok_chat.reset(user.id)
        await update.message.reply_text("Chat reiniciado.")


async def level_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    args = context.args or []

    if not args:
        current = grok_chat.get_level(user.id)
        await update.message.reply_text(
            f"Nivel actual: *{current}*\n\n"
            "• `suave` → coqueta y sugerente, sin lenguaje explícito\n"
            "• `medio` → caliente y directa, sin descripciones gráficas\n"
            "• `alto` → roleplay adulto explícito\n\n"
            "Cambiar: `/nivel alto`",
            parse_mode="Markdown",
        )
        return

    level = args[0].lower()
    if not grok_chat.set_level(user.id, level):
        await update.message.reply_text("Nivel inválido. Usá: suave, medio o alto.")
        return

    await update.message.reply_text(
        f"Listo, nivel de explicitud: *{grok_chat.get_level(user.id)}*. Reinicié los chats.",
        parse_mode="Markdown",
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model_key = context.user_data.get("model")
    if model_key:
        name = MODELS[model_key]["name"]
        text = update.message.text or ""
        reply = None
        if grok_chat.is_enabled() and update.effective_user:
            reply = grok_chat.chat(update.effective_user.id, model_key, text)
        if not reply:
            reply = f"{name}: {random.choice(FREE_TEXT_REPLIES)}"
        await update.message.reply_text(reply, reply_markup=model_menu_keyboard(model_key))
    else:
        await update.message.reply_text("Usá /start para elegir una modelo 👇", reply_markup=model_keyboard())


async def error_handler(update, context):
    logger.exception("Error no manejado", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    request = HTTPXRequest(connect_timeout=20, read_timeout=120, write_timeout=120, pool_timeout=20)
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roles", roles_command))
    app.add_handler(CommandHandler(["rol", "perfil"], role_command))
    app.add_handler(CommandHandler("persona", persona_command))
    app.add_handler(CommandHandler("nivel", level_command))
    app.add_handler(CommandHandler("reset", reset_command))
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
