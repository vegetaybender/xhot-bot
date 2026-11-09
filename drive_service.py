import io
import json
import logging
import os
import random
import time

logger = logging.getLogger(__name__)

MAX_VIDEO_BYTES = int(os.getenv("MAX_VIDEO_MB", "20")) * 1024 * 1024
_FILES_CACHE = {}
_CACHE_TTL = 300  # segundos

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import MODELS, DRIVE_ROOT_FOLDER_ID

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

_service = None
_folder_cache = {}


def get_service():
    global _service
    if _service is not None:
        return _service

    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            import base64
            decoded = base64.b64decode(raw).decode("utf-8")
            info = json.loads(decoded)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        path = os.getenv("GOOGLE_CREDENTIALS_FILE", "").strip()
        if not path:
            raise RuntimeError("Falta GOOGLE_SERVICE_ACCOUNT_JSON o GOOGLE_CREDENTIALS_FILE")
        creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

    _service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _service


def _escape(name):
    return name.replace("\\", "\\\\").replace("'", "\\'")


def find_subfolder(parent_id, name):
    service = get_service()
    q = (
        f"'{parent_id}' in parents and "
        f"name = '{_escape(name)}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    resp = service.files().list(q=q, fields="files(id,name)", pageSize=10).execute()
    files = resp.get("files", [])
    if not files:
        return None
    return files[0]["id"]


def get_model_folder_id(model_key):
    if model_key in _folder_cache:
        return _folder_cache[model_key]

    folder_name = MODELS[model_key]["folder"]
    root = os.getenv("DRIVE_ROOT_FOLDER_ID", DRIVE_ROOT_FOLDER_ID)
    fid = find_subfolder(root, folder_name)
    if not fid:
        raise RuntimeError(f"No se encontró la carpeta '{folder_name}' en Drive")
    logger.info("Carpeta modelo %s -> %s", model_key, fid)
    _folder_cache[model_key] = fid
    return fid


def list_files(folder_id):
    """Lista archivos directos de una carpeta (sin recursión)."""
    service = get_service()
    files = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id,name,mimeType,size)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def list_files_recursive(root_folder_id):
    """Recorre la carpeta y todas sus subcarpetas, devolviendo todos los archivos."""
    collected = []
    stack = [root_folder_id]
    visited = set()
    while stack:
        fid = stack.pop()
        if fid in visited:
            continue
        visited.add(fid)
        for f in list_files(fid):
            mime = f.get("mimeType", "")
            if mime == "application/vnd.google-apps.folder":
                stack.append(f["id"])
            else:
                collected.append(f)
    return collected


def get_cached_files(model_key, folder_id):
    now = time.time()
    entry = _FILES_CACHE.get(model_key)
    if entry and (now - entry[0]) < _CACHE_TTL:
        return entry[1]
    files = list_files_recursive(folder_id)
    _FILES_CACHE[model_key] = (now, files)
    return files


def _is_image(mime):
    return mime.startswith("image/")


def _is_video(mime):
    return mime.startswith("video/")


def get_random_media(model_key, kind="any"):
    """kind: 'image', 'video' or 'any'"""
    fid = get_model_folder_id(model_key)
    files = get_cached_files(model_key, fid)
    logger.info("Modelo %s: %d archivos (recursivo)", model_key, len(files))

    def ok(f):
        m = f.get("mimeType", "")
        size = int(f.get("size") or 0)
        if kind == "image":
            if not _is_image(m):
                return False
        elif kind == "video":
            if not _is_video(m):
                return False
            if size and size > MAX_VIDEO_BYTES:
                return False
        else:
            if _is_image(m):
                pass
            elif _is_video(m):
                if size and size > MAX_VIDEO_BYTES:
                    return False
            else:
                return False
        return True

    candidates = [f for f in files if ok(f)]
    logger.info("Modelo %s: %d candidatos (kind=%s)", model_key, len(candidates), kind)
    if not candidates:
        return None
    return random.choice(candidates)


def download_file(file_id):
    service = get_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request, chunksize=5 * 1024 * 1024)


def get_random_album(model_key, count=3):
    """Devuelve `count` fotos. Prefiere un mismo subconjunto (carpeta con >=count fotos); si no, aleatorio global."""
    fid = get_model_folder_id(model_key)
    folders_with_enough = []
    all_images = []
    stack = [fid]
    visited = set()
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        direct = list_files(cur)
        imgs = [f for f in direct if _is_image(f.get("mimeType", ""))]
        if len(imgs) >= count:
            folders_with_enough.append(imgs)
        all_images.extend(imgs)
        for f in direct:
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                stack.append(f["id"])

    if folders_with_enough:
        pool = random.choice(folders_with_enough)
    else:
        pool = all_images

    if not pool:
        return []
    if len(pool) <= count:
        return list(pool)
    return random.sample(pool, count)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh
