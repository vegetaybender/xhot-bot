import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DRIVE_ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", "1zpDaUJvluGwE8n5YboC2bxViieWaLn9F")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

# model key -> display name + Drive subfolder name
MODELS = {
    "yus": {"name": "Yus López", "folder": "Yus Lopez"},
    "angie": {"name": "Angie Watters", "folder": "Angie Watters"},
    "valen": {"name": "Valen Borelli", "folder": "Valen Borelli"},
}

FREE_TEXT_REPLIES = [
    "Estoy acá 😘 pedime una foto o un video cuando quieras.",
    "Hola hermoso/a 💋 ¿querés ver algo mío?",
    "Mmm... me gusta que escribas ✨ pedime contenido.",
    "Estoy un poco ocupada, pero te mando algo si me lo pedís 📸",
    "¿Querés una foto o un video? Tocá los botones de abajo 👇",
]
