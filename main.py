import io
import logging
import os
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.error import BadRequest, Forbidden, TelegramError
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
import vision

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def md(text):
    """Escapa los _ fuera de `código`: Telegram los toma como entidades."""
    out = []
    in_code = False
    for ch in (text or ""):
        if ch == "`":
            in_code = not in_code
            out.append(ch)
        elif ch == "_" and not in_code:
            out.append("\\_")
        else:
            out.append(ch)
    return "".join(out)


# Chats con "vida propia" activada. Todo el estado (modo incluido) es en memoria:
# se resetea al redeployar y el usuario debe volver a activarlo con /vida.
VIDA_CHATS = set()

VIDA_FALLBACKS = {
    "novia": [
        "Ay, amor, se me ocurrió mandarte esta foto sin que me la pidas 🥺 "
        "¿Me decís qué te parece y charlamos? 💕",
        "Estaba pensando en vos y me saqué esta foto... ¿venís a hablar conmigo? 😘",
    ],
    "amante": [
        "Me aparecí de la nada porque estaba caliente pensando en vos... "
        "¿te animás a chatear? 😈",
        "Te mandé esto mío sin avisar. Ahora quiero que me escribas y me digas qué te gustó 🔥",
    ],
    "vip": [
        "Esta es una muestra gratis de mi tiempo 😏 Si querés seguir chateando, ya sabés cómo se hace.",
        "Te mandé una muestra de mi agenda. ¿Vas a escribirme o te quedás con las ganas? 💋",
    ],
}


def register_vida(chat_id):
    VIDA_CHATS.add(chat_id)


def unregister_vida(chat_id):
    VIDA_CHATS.discard(chat_id)


def sync_vida(update, context):
    """Mantiene el registro de chats automáticos según el modo guardado."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    if grok_chat.get_mode(user.id) == "vida":
        register_vida(chat.id)
    else:
        unregister_vida(chat.id)


# --- Reenvío desde un grupo a contacto y/o canal ---------------------------
def _parse_ids(raw):
    ids = []
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return ids


def _forward_group_id():
    ids = _parse_ids(os.getenv("FORWARD_GROUP_ID", ""))
    return ids[0] if ids else None


def _forward_destinations():
    ids = _parse_ids(os.getenv("FORWARD_DEST_IDS", ""))
    ids += _parse_ids(os.getenv("FORWARD_CONTACT_ID", ""))
    ids += _parse_ids(os.getenv("FORWARD_CHANNEL_ID", ""))
    seen = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def _forward_mode():
    mode = os.getenv("FORWARD_MODE", "forward").strip().lower()
    return mode if mode in ("forward", "copy") else "forward"


def _env_int(name):
    ids = _parse_ids(os.getenv(name, ""))
    return ids[0] if ids else None


# topic elegido por grupo: {"source": thread_id | None, "dest": thread_id | None}
FORWARD_TOPICS = {}


def _source_thread(chat_id):
    per_chat = FORWARD_TOPICS.get(chat_id, {}).get("source")
    return per_chat if per_chat is not None else _env_int("FORWARD_THREAD_ID")


def _dest_thread(chat_id):
    per_chat = FORWARD_TOPICS.get(chat_id, {}).get("dest")
    return per_chat if per_chat is not None else _env_int("FORWARD_DEST_THREAD_ID")


try:
    _NO_STATUS_UPDATES = ~filters.StatusUpdate.ALL
except AttributeError:
    _NO_STATUS_UPDATES = filters.ALL

FORWARD_FILTER = filters.ChatType.GROUPS & ~filters.COMMAND & _NO_STATUS_UPDATES


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
        [InlineKeyboardButton("⚙️ Modo", callback_data="action:modes"),
         InlineKeyboardButton("🔄 Cambiar modelo", callback_data="action:models")],
        [InlineKeyboardButton("🏠 Menú principal", callback_data="action:menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def modes_keyboard(user_id):
    current = grok_chat.get_mode(user_id)
    buttons = []
    for key in grok_chat.mode_names():
        label = grok_chat.mode_label(key)
        if key == current:
            label = f"✅ {label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"mode:{key}")])
    buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="action:back")])
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("model", None)
    if update.effective_user:
        grok_chat.reset(update.effective_user.id)
    sync_vida(update, context)
    text = (
        "Hola 👋 Bienvenido/a a *Xhot* 🔥\n\n"
        "Elegí una modelo para chatear:\n\n"
        "Después podés cambiar su rol con /rol (novia, amante, vip), el nivel con /nivel "
        "y el modo con /modo (archivos, rol, rol_fotos, vida).\n\n"
        "Con `/modo vida` (o `/vida`) el bot cobra vida propia: de vez en cuando "
        "te manda una foto de una modelo al azar, la describe y te invita a chatear. 💌"
    )
    text = md(text)
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
        level = grok_chat.get_level(update.effective_user.id) if update.effective_user else "alto"
        mode = grok_chat.get_mode(update.effective_user.id) if update.effective_user else "rol_fotos"
        await query.edit_message_text(
            f"Ahora estás chateando con *{name}* 💬\n"
            f"Rol: *{role}* · Nivel: *{level}*\n"
            f"Modo: *{grok_chat.mode_label(mode)}*\n"
            "Cambiá el rol con /rol, el nivel con /nivel y el modo con /modo\n"
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

    if data == "action:modes":
        if not update.effective_user:
            return
        current = grok_chat.get_mode(update.effective_user.id)
        await query.edit_message_text(
            f"Modo actual: *{grok_chat.mode_label(current)}*\n\n"
            "Elegí cómo querés que funcione el bot:",
            reply_markup=modes_keyboard(update.effective_user.id),
            parse_mode="Markdown",
        )
        return

    if data.startswith("mode:"):
        if not update.effective_user:
            return
        mode = data.split(":", 1)[1]
        if not grok_chat.set_mode(update.effective_user.id, mode):
            await query.edit_message_text("Modo inválido.")
            return
        sync_vida(update, context)
        model_key = context.user_data.get("model")
        label = grok_chat.mode_label(grok_chat.get_mode(update.effective_user.id))
        extra = (
            "\n\nAhora el bot tiene vida propia: te va a mandar fotos de una modelo al azar "
            "y te va a invitar a chatear, sin que se lo pidas. 💌"
            if grok_chat.get_mode(update.effective_user.id) == "vida"
            else "\n\nYa podés pedir fotos o escribirle a la modelo."
        )
        if model_key:
            await query.edit_message_text(
                f"Modo activado: *{label}*{extra}",
                reply_markup=model_menu_keyboard(model_key),
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(
                f"Modo activado: *{label}*{extra}\n\nElegí una modelo:",
                reply_markup=model_keyboard(),
                parse_mode="Markdown",
            )
        return

    if data == "action:back":
        model_key = context.user_data.get("model")
        if model_key:
            await query.edit_message_text(
                f"Elegí una opción para *{MODELS[model_key]['name']}*:",
                reply_markup=model_menu_keyboard(model_key),
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("Elegí una modelo:", reply_markup=model_keyboard())
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
        album_images = []
        for img in images:
            try:
                fh = download_file(img["id"])
            except Exception as e:
                logger.exception("Error descargando archivo")
                await query.message.reply_text("No pude descargar una foto 😕", reply_markup=model_menu_keyboard(model_key))
                continue
            album_images.append((fh.getvalue(), img.get("mimeType", "image/jpeg")))
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
            mode = grok_chat.get_mode(update.effective_user.id)
            if mode == "archivos":
                await query.message.reply_text(
                    "¿Qué más querés ver? 👇",
                    reply_markup=model_menu_keyboard(model_key),
                )
                return

            album_desc = None
            if mode in ("rol_fotos", "vida"):
                album_desc = vision.describe_images(
                    album_images,
                    kind="album",
                    cache_key=tuple(img["id"] for img in images),
                )
                grok_chat.note_media(
                    update.effective_user.id,
                    model_key,
                    album_desc or "sin descripción",
                    kind="album",
                    read=bool(album_desc),
                )

            chat_reply = None
            prompt = ""
            if grok_chat.is_enabled():
                if mode in ("rol_fotos", "vida") and album_desc:
                    prompt = (
                        "Instrucción interna: el usuario acaba de recibir tu álbum de fotos. "
                        f"En las fotos se ve: {album_desc}. "
                        "Escribí tu próximo mensaje como la modelo que lo mandó, en 1-2 frases, "
                        "mencionando al menos un detalle concreto y ofreciendo mandar otra. "
                        "No repitas la lista tal cual."
                    )
                else:
                    prompt = (
                        "Instrucción interna: el usuario acaba de recibir tu álbum de fotos. "
                        "Escribí tu próximo mensaje como la modelo que lo mandó, en 1-2 frases, "
                        "y ofrecé mandar otra."
                    )
                chat_reply = grok_chat.chat(update.effective_user.id, model_key, prompt)
            if not chat_reply:
                chat_reply = grok_chat.fallback_reply(update.effective_user.id, model_key, prompt)
            await query.message.reply_text(chat_reply, reply_markup=model_menu_keyboard(model_key))
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

    mime = media.get("mimeType", "")

    if mime.startswith("video/"):
        await query.edit_message_text("Descargando video... ⏳")
    try:
        fh = download_file(media["id"])
    except Exception as e:
        logger.exception("Error descargando archivo")
        await query.edit_message_text("No pude descargar el archivo 😕", reply_markup=model_menu_keyboard(model_key))
        return

    file_bytes = fh.getvalue()
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
        mode = grok_chat.get_mode(update.effective_user.id)
        if mode == "archivos":
            await query.message.reply_text(
                "¿Qué más querés ver? 👇",
                reply_markup=model_menu_keyboard(model_key),
            )
            return

        is_video = mime.startswith("video/")
        description = None
        if mode in ("rol_fotos", "vida"):
            if not is_video:
                description = vision.describe_images(
                    [(file_bytes, mime)],
                    kind="foto",
                    cache_key=media["id"],
                )
            if description:
                media_desc = description
            elif is_video:
                media_desc = media["name"][:40]
            else:
                media_desc = "sin descripción"
            grok_chat.note_media(
                update.effective_user.id,
                model_key,
                media_desc,
                kind="video" if is_video else "foto",
                read=bool(description) if not is_video else False,
            )

        chat_reply = None
        prompt = ""
        if grok_chat.is_enabled():
            media_word = "video" if is_video else "foto"
            if mode in ("rol_fotos", "vida") and description:
                prompt = (
                    f"Instrucción interna: el usuario acaba de recibir tu {media_word}. "
                    f"En la foto se ve: {description}. "
                    "Escribí tu próximo mensaje como la modelo que la mandó, en 1-2 frases, "
                    "mencionando al menos un detalle concreto y ofreciendo mandar otra. "
                    "No repitas la lista tal cual."
                )
            else:
                prompt = (
                    f"Instrucción interna: el usuario acaba de recibir tu {media_word}. "
                    "Escribí tu próximo mensaje como la modelo que la mandó, en 1-2 frases, "
                    "y ofrecé mandar otra."
                )
            chat_reply = grok_chat.chat(update.effective_user.id, model_key, prompt)
        if not chat_reply:
            chat_reply = grok_chat.fallback_reply(update.effective_user.id, model_key, prompt)
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
            "• `alto` → roleplay adulto explícito y sin filtros (alias: extremo)\n\n"
            "Cambiar: `/nivel alto` o `/nivel extremo`",
            parse_mode="Markdown",
        )
        return

    level = args[0].lower()
    if not grok_chat.set_level(user.id, level):
        await update.message.reply_text("Nivel inválido. Usá: suave, medio, alto o extremo.")
        return

    await update.message.reply_text(
        f"Listo, nivel de explicitud: *{grok_chat.get_level(user.id)}*. Reinicié los chats.",
        parse_mode="Markdown",
    )


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    args = context.args or []

    if not args:
        current = grok_chat.get_mode(user.id)
        await update.message.reply_text(
            md(
                f"Modo actual: *{grok_chat.mode_label(current)}*\n\n"
                "• `archivos` → solo fotos/videos, sin rol\n"
                "• `rol` → chat con rol, sin interpretar fotos\n"
                "• `rol_fotos` → chat con rol + interpreta las fotos\n"
                "• `vida` → además, mensajes automáticos con foto de una modelo al azar\n\n"
                "Cambiar: `/modo archivos`, `/modo rol`, `/modo rol_fotos` o `/modo vida`"
            ),
            reply_markup=modes_keyboard(user.id),
            parse_mode="Markdown",
        )
        return

    mode = args[0].lower()
    if not grok_chat.set_mode(user.id, mode):
        await update.message.reply_text("Modo inválido. Usá: archivos, rol, rol_fotos o vida.")
        return

    sync_vida(update, context)
    extra = (
        "\n\nVida propia activada 💌: de vez en cuando te voy a mandar una foto de una modelo "
        "al azar, la voy a describir y te voy a invitar a chatear."
        if grok_chat.get_mode(user.id) == "vida"
        else ""
    )
    await update.message.reply_text(
        f"Listo, modo: *{grok_chat.mode_label(grok_chat.get_mode(user.id))}*. Reinicié los chats.{extra}",
        parse_mode="Markdown",
    )


async def vida_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    args = context.args or []
    if args and args[0].lower() in ("off", "stop", "apagar", "no"):
        grok_chat.set_mode(user.id, "rol_fotos")
        sync_vida(update, context)
        await update.message.reply_text(md("Vida propia desactivada. Volvemos a modo *rol_fotos*."), parse_mode="Markdown")
        return

    grok_chat.set_mode(user.id, "vida")
    sync_vida(update, context)
    await update.message.reply_text(
        md(
            "Vida propia activada 💌\n\n"
            "De vez en cuando te voy a mandar una foto de Yus, Angie o Valen al azar. "
            "Voy a leer la foto con visión, te voy a describir lo que se ve en personaje "
            "y te voy a invitar a chatear con ella, con su rol ya seteado.\n\n"
            "Para apagarlo: `/vida off` o `/modo rol_fotos`."
        ),
        parse_mode="Markdown",
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sync_vida(update, context)
    model_key = context.user_data.get("model")
    if model_key:
        mode = grok_chat.get_mode(update.effective_user.id) if update.effective_user else "archivos"
        if mode == "archivos":
            await update.message.reply_text(
                md(
                    "Modo *solo archivos* activo. Usá los botones para pedir fotos, álbumes o videos.\n"
                    "Para activar el rol: /modo rol o /modo rol_fotos. Para vida propia: /vida"
                ),
                reply_markup=model_menu_keyboard(model_key),
                parse_mode="Markdown",
            )
            return

        text = update.message.text or ""
        reply = None
        if grok_chat.is_enabled() and update.effective_user:
            reply = grok_chat.chat(update.effective_user.id, model_key, text)
        if not reply:
            if update.effective_user:
                reply = grok_chat.fallback_reply(update.effective_user.id, model_key, text)
            else:
                reply = random.choice(FREE_TEXT_REPLIES)
        await update.message.reply_text(reply, reply_markup=model_menu_keyboard(model_key))
    else:
        await update.message.reply_text("Usá /start para elegir una modelo 👇", reply_markup=model_keyboard())


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.message
    user = update.effective_user
    if not chat or not message:
        return
    lines = [
        "*IDs de este chat*",
        f"• Chat ID: `{chat.id}`",
        f"• Tipo: `{chat.type}`",
    ]
    thread_id = getattr(message, "message_thread_id", None)
    if thread_id:
        lines.append(f"• Topic/hilo ID: `{thread_id}`")
    if user:
        lines.append(f"• Tu user ID: `{user.id}`")
    lines += [
        "",
        "Copiá en Railway según corresponda:",
        f"• Grupo origen → `FORWARD_GROUP_ID={chat.id}`",
        f"• Contacto destino → `FORWARD_CONTACT_ID={user.id if user else chat.id}`",
        f"• Canal destino → `FORWARD_CHANNEL_ID={chat.id}`",
        "",
        "Para elegir temas (topics):",
        "• Escribí `/settopic` dentro del topic de origen.",
        "• `/settopic 123` → ese topic de origen y el topic `123` como destino.",
        "• `/settopic off` → volver a reenviar todo, sin filtrar por topic.",
    ]
    await message.reply_text(md("\n".join(lines)), parse_mode="Markdown")


async def settopic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elegí el topic de origen (donde llamás al bot) y el topic de destino."""
    chat = update.effective_chat
    message = update.message
    if not chat or not message:
        return

    args = context.args or []
    if args and args[0].lower() in ("off", "todo", "todos", "reset", "limpiar"):
        FORWARD_TOPICS.pop(chat.id, None)
        await message.reply_text(
            md("Listo: reenvío sin filtro de topic otra vez."),
            parse_mode="Markdown",
        )
        return

    source = getattr(message, "message_thread_id", None)
    if not source:
        await message.reply_text(
            md(
                "Este comando tiene que escribirse *dentro de un topic* del grupo. "
                "Ahí es donde el bot va a escuchar los mensajes."
            ),
            parse_mode="Markdown",
        )
        return

    dest = None
    if args:
        ids = _parse_ids(args[0])
        dest = ids[0] if ids else None

    FORWARD_TOPICS[chat.id] = {"source": source, "dest": dest}
    dest_text = f"`{dest}`" if dest is not None else "el mismo topic en el destino"
    await message.reply_text(
        md(
            f"Listo ✅\n\n"
            f"• Topic de origen: `{source}`\n"
            f"• Topic de destino: {dest_text}\n\n"
            "De ahora en adelante solo reenvío los mensajes de ese topic. "
            "Si el destino es un canal (sin topics) y falla, lo reintento sin topic."
        ),
        parse_mode="Markdown",
    )


async def ignore_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """En grupos el bot solo reenvía: ignora comandos que no sean /chatid ni /settopic."""
    return


async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    if not message or not chat:
        return

    sender = message.from_user
    if sender and sender.is_bot:
        return

    group_id = _forward_group_id()
    if group_id is not None and chat.id != group_id:
        return

    source_thread = _source_thread(chat.id)
    if source_thread is not None and getattr(message, "message_thread_id", None) != source_thread:
        return

    destinations = _forward_destinations()
    if not destinations:
        return

    mode = _forward_mode()
    dest_thread = _dest_thread(chat.id)
    if dest_thread is None and source_thread is not None:
        # Por defecto el mismo número de topic en el destino.
        dest_thread = source_thread

    for dest in destinations:
        for use_thread in (True, False) if dest_thread is not None else (False,):
            thread = dest_thread if use_thread else None
            try:
                kwargs = {"message_thread_id": thread} if thread is not None else {}
                if mode == "copy":
                    await context.bot.copy_message(
                        chat_id=dest,
                        from_chat_id=chat.id,
                        message_id=message.message_id,
                        **kwargs,
                    )
                else:
                    await context.bot.forward_message(
                        chat_id=dest,
                        from_chat_id=chat.id,
                        message_id=message.message_id,
                        **kwargs,
                    )
                break
            except Forbidden:
                logger.warning("Reenvío a %s: el bot no tiene permiso para escribir", dest)
                break
            except BadRequest as e:
                msg = str(e).lower()
                if use_thread and any(
                    word in msg for word in ("thread", "topic", "forum", "message_thread_id")
                ):
                    logger.info("El destino %s no acepta topics; reintento sin topic", dest)
                    continue
                logger.warning("No pude reenviar el mensaje a %s: %s", dest, e)
                break
            except TelegramError as e:
                logger.warning("No pude reenviar el mensaje a %s: %s", dest, e)
                break


async def vida_job(context: ContextTypes.DEFAULT_TYPE):
    """Mensaje automático: foto al azar + descripción + invitación a chatear."""
    if not VIDA_CHATS:
        return

    for chat_id in list(VIDA_CHATS):
        model_key = random.choice(list(MODELS.keys()))
        try:
            media = get_random_media(model_key, "image")
            if not media:
                continue
            mime = media.get("mimeType", "") or ""
            if not mime.startswith("image/"):
                continue

            fh = download_file(media["id"])
            file_bytes = fh.getvalue()
            size = int(media.get("size") or 0)
            if size and size > 45 * 1024 * 1024:
                continue

            description = vision.describe_images(
                [(file_bytes, mime)],
                kind="foto",
                cache_key=media["id"],
            )
            grok_chat.note_media(
                chat_id,
                model_key,
                description or "sin descripción",
                kind="foto",
                read=bool(description),
            )

            role = grok_chat.get_role(chat_id, model_key)
            if description:
                prompt = (
                    "Instrucción interna: recién le mandaste una foto tuya sin que te la pida. "
                    f"En la foto se ve: {description}. "
                    "Escribí 1 o 2 frases en personaje: describí con picardía un detalle concreto "
                    "y terminá invitándolo a que te escriba y chatee con vos. "
                    "No repitas la descripción literal ni menciones esta instrucción."
                )
            else:
                prompt = (
                    "Instrucción interna: recién le mandaste una foto tuya sin que te la pida. "
                    "Escribí 1 o 2 frases en personaje y terminá invitándolo a que te escriba "
                    "y chatee con vos. No menciones esta instrucción."
                )

            reply = None
            if grok_chat.is_enabled():
                reply = grok_chat.chat(chat_id, model_key, prompt)
            if not reply:
                reply = random.choice(VIDA_FALLBACKS.get(role, VIDA_FALLBACKS["novia"]))

            # La foto va sin caption; el texto sale en un mensaje aparte con los botones.
            await context.bot.send_photo(chat_id=chat_id, photo=file_bytes)
            user_data = context.application.user_data
            if chat_id not in user_data:
                user_data[chat_id] = {}
            user_data[chat_id]["model"] = model_key
            await context.bot.send_message(
                chat_id=chat_id,
                text=reply,
                reply_markup=model_menu_keyboard(model_key),
            )
            logger.info("Vida: mensaje automático enviado a %s con %s (%s)", chat_id, model_key, role)
        except Forbidden:
            unregister_vida(chat_id)
            logger.info("Vida: el usuario %s bloqueó el bot; se lo quitó del registro", chat_id)
        except Exception:
            logger.exception("Vida: error enviando mensaje automático a %s", chat_id)


async def error_handler(update, context):
    logger.exception("Error no manejado", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Falta BOT_TOKEN")

    logger.info("Xhot Bot - modos disponibles: %s", ", ".join(grok_chat.mode_names()))
    request = HTTPXRequest(connect_timeout=20, read_timeout=120, write_timeout=120, pool_timeout=20)
    app = Application.builder().token(BOT_TOKEN).request(request).build()
    # En grupos el bot solo reenvía; /chatid es la única excepción.
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.COMMAND & ~filters.Command(["chatid", "settopic"]),
        ignore_group_command,
    ))
    app.add_handler(CommandHandler("chatid", chatid_command))
    app.add_handler(CommandHandler("settopic", settopic_command))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roles", roles_command))
    app.add_handler(CommandHandler(["rol", "perfil"], role_command))
    app.add_handler(CommandHandler("persona", persona_command))
    app.add_handler(CommandHandler("nivel", level_command))
    app.add_handler(CommandHandler("modo", mode_command))
    app.add_handler(CommandHandler("vida", vida_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(FORWARD_FILTER, forward_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    interval = max(1, int(os.getenv("VIDA_INTERVAL_MINUTES", "30"))) * 60
    first = max(1, int(os.getenv("VIDA_FIRST_MINUTES", "2"))) * 60
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            vida_job,
            interval=interval,
            first=first,
            name="vida_propia",
        )
        logger.info("Vida propia: cada %d min (primer mensaje en %d min)", interval // 60, first // 60)
    else:
        logger.warning("Vida propia desactivada: el bot no tiene JobQueue disponible")

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
