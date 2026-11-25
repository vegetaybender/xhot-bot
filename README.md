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

## Reenvío desde un grupo a un contacto y/o un canal

El bot puede reenviar **todo tipo de mensaje** (texto, fotos, videos, audios, documentos,
álbumes) desde un grupo que ya tenés hacia un contacto y un canal a la vez. En el grupo
queda **silencioso**: no responde con roleplay ni con comandos (salvo `/chatid` y `/settopic`).

Configuración paso a paso:

1. En BotFather hacé `/setprivacy` → elegí el bot → **Disable**. Si no, Telegram solo le
   entrega al bot los comandos y las respuestas dirigidas a él, no el resto del grupo.
2. Agregá al bot al grupo de origen.
3. Si va a publicar en un canal, agregalo como **administrador** con permiso de publicar.
4. Escribí `/chatid` en el grupo y en el chat del contacto, y copiá los IDs. Para el canal,
   reenviá un mensaje suyo a un bot tipo `@get_id_bot` (o mirá el ID en la URL de Telegram Web).
5. Cargá en Railway:

   - `FORWARD_GROUP_ID` → ID del grupo de origen (si lo dejás vacío, reenvía desde cualquier grupo).
   - `FORWARD_CONTACT_ID` → ID del contacto destino.
   - `FORWARD_CHANNEL_ID` → ID del canal destino.
   - `FORWARD_DEST_IDS` → alternativa: ambos IDs en una sola lista separada por coma.
   - `FORWARD_MODE` → `forward` (default, conserva el encabezado "Reenviado desde…") o `copy`
     (publica una copia limpia, sin el encabezado).

6. **Elegir topics (opcional)**: entrá al topic del grupo desde el que querés reenviar y escribí:

   - `/settopic` → solo se reenvían los mensajes de ese topic y se publican en el topic del
     mismo número en el destino.
   - `/settopic 123` → origen = el topic actual, destino = topic `123`.
   - `/settopic off` → volver a reenviar todo el grupo, sin filtrar.

   También podés fijarlos con `FORWARD_THREAD_ID` (origen) y `FORWARD_DEST_THREAD_ID` (destino).
   Si el destino es un canal (no tiene topics), el bot reintenta automáticamente sin topic.

7. Redeploy para que tome las variables.

Notas: los álbumes se reenvían foto por foto (Telegram no permite reenviar el grupo completo
como una sola unidad). Los mensajes de servicio (nuevos miembros, cambios de título, etc.)
se ignoran. Si el bot es el autor del mensaje, también se ignora para evitar bucles.

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
