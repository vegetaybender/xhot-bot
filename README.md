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

## Modos

- `/modo archivos` → solo fotos/videos, sin IA (como era al principio).
- `/modo rol` → chat con rol, pero sin interpretar las fotos.
- `/modo rol_fotos` → chat con rol + interpreta las fotos (default).
- `/modo vida` (o `/vida`) → **vida propia**: el bot te manda mensajes automáticos.

También se puede cambiar desde el botón **⚙️ Modo** del menú.
El modo por defecto es `rol_fotos`; si querés que arranque en solo archivos,
definí `CHAT_MODE=archivos` en Railway.

### Vida propia (`/vida`)

Cuando activás este modo, cada cierto tiempo el bot toma la iniciativa:

1. Elige una modelo al azar entre Yus López, Angie Watters y Valen Borelli.
2. Busca una foto suya en Drive y te la manda **sin caption**.
3. La lee con visión (Gemini) y describe lo que se ve.
4. Te manda un mensaje aparte, en personaje y con el **rol ya seteado de esa modelo**
   (novia / amante / vip), invitándote a chatear, con los botones del menú.

Si la visión no está configurada o falla, igual se manda la foto y el mensaje de invitación.
Para apagarlo: `/vida off` o `/modo rol_fotos`.

Intervalos configurables en Railway:

- `VIDA_INTERVAL_MINUTES` → minutos entre mensajes automáticos (default `30`).
- `VIDA_FIRST_MINUTES` → minutos hasta el primer mensaje (default `2`).

Para que los mensajes automáticos funcionen, `requirements.txt` instala
`python-telegram-bot[job-queue]` (sin ese extra el bot arranca pero avisa
`No JobQueue set up` y el modo `vida` queda inactivo).

El registro de chats (y los modos, roles y niveles) vive en memoria: después de un
redeploy hay que volver a activarlo con `/vida` (o `/modo vida`). Si el proceso se
reinicia sin redeploy, se re-registra automáticamente cuando el usuario escribe o
usa `/start`.

## Búsqueda de mensajes viejos entre topics (`/BUSQUEDA`)

El bot trabaja **dentro de un mismo grupo con Temas**. Ya no reenvía automáticamente a
contactos ni canales: cuando se lo pedís, toma un mensaje viejo de un topic **origen**
y lo publica en un topic **destino**. En el grupo queda silencioso: no responde con
roleplay ni con otros comandos.

Configuración paso a paso:

1. En BotFather hacé `/setprivacy` → elegí el bot → **Disable**. Si no, Telegram solo le
   entrega al bot los comandos, no los mensajes del grupo.
2. Agregá al bot al grupo con Temas.
3. Entrá al topic de origen y escribí `/setorigen` (o `/setorigen 123` si ya sabés el ID).
4. Entrá al topic de destino y escribí `/setdestino` (o `/setdestino 456`).
5. Escribí `/BUSQUEDA` en el destino. El bot reenvía un mensaje al azar del origen y deja
   un botón **🔎 Otra búsqueda**. Cada toque trae otro mensaje, sin repetir hasta agotar
   los guardados (después vuelve a empezar el ciclo).
6. `/chatid` muestra el ID del topic actual, por si querés pasarlo como argumento.

Opcional en Railway:

- `BUSQUEDA_MODE` → `forward` (default, conserva el encabezado "Reenviado desde…") o `copy`
  (publica una copia limpia, sin el encabezado).
- `BUSQUEDA_HISTORY_LIMIT` → cuántos mensajes por topic se guardan en memoria (default `500`).

**Limitación importante:** la API de bots de Telegram no puede leer mensajes anteriores a
que el bot entrara al grupo. Solo se pueden buscar los mensajes que el bot vio mientras
estuvo en el grupo con la privacidad desactivada. Los álbumes se guardan foto por foto;
los mensajes de servicio y los comandos se ignoran.

El estado (topics elegidos e historial) vive en memoria: se resetea al redeploy y hay que
marcar otra vez los topics con `/setorigen` y `/setdestino`.

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
- `chat_ai.py` → roleplay, roles, niveles, modos e historial
- `vision.py` → descripción de fotos con Gemini
- `drive_service.py` → integración con Google Drive
- `config.py` → configuración y modelos
