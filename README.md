# Xhot Bot

Bot de Telegram semi-automático para las modelos: Yus López, Angie Watters y Valen Borelli.
Envía fotos/videos aleatorios desde las carpetas de Google Drive.

## Variables de entorno (Railway)

- `BOT_TOKEN` → Token del bot de Telegram (@Xhotv1_bot)
- `GOOGLE_SERVICE_ACCOUNT_JSON` → Contenido completo del JSON de la cuenta de servicio (en una sola línea)
- `DRIVE_ROOT_FOLDER_ID` → `1zpDaUJvluGwE8n5YboC2bxViieWaLn9F`
- `WEBHOOK_URL` → URL pública de Railway, ej. `https://tu-app.up.railway.app`
- `PORT` → Railway lo inyecta automáticamente

## Roles y niveles

- `/rol novia` → sumisa y obediente, busca aprobación.
- `/rol amante` → espontánea y erótica, manda contenido de la nada.
- `/rol vip` → escort VIP: el usuario paga y ella hace que pida más.
- `/nivel suave` → coqueta, sin lenguaje explícito.
- `/nivel medio` → caliente y directa, sin descripciones gráficas.
- `/nivel alto` (o `/nivel extremo`) → roleplay adulto explícito y sin filtros.

Todas las modelos hablan en español rioplatense con voseo. El nivel por defecto es `alto`
(si `CHAT_EXPLICIT_LEVEL` está definido en Railway, ese valor tiene prioridad).

## Deploy en Railway

1. Crear un nuevo proyecto en Railway.app → "Deploy from GitHub" o subir esta carpeta.
2. Agregar las variables de entorno en la pestaña **Variables**.
3. Para `GOOGLE_SERVICE_ACCOUNT_JSON`: abrir el archivo JSON descargado, copiar todo su contenido y pegarlo como valor (sin saltos de línea).
4. Railway genera un dominio público (Settings → Domains). Copiarlo y ponerlo en `WEBHOOK_URL` (sin barra final).
5. Redeploy para que tome el webhook.

## Ejecución local (opcional)

```bash
pip install -r requirements.txt
cp .env.example .env
# completar .env
python main.py
```

Sin `WEBHOOK_URL`, el bot corre en modo polling (útil para pruebas locales).

## Estructura

- `main.py` → lógica del bot y handlers
- `drive_service.py` → integración con Google Drive
- `config.py` → configuración y modelos
