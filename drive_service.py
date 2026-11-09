import io
import json
import os
import random

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
    _folder_cache[model_key] = fid
    return fid


def list_files(folder_id):
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


def _is_image(mime):
    return mime.startswith("image/")


def _is_video(mime):
    return mime.startswith("video/")


def get_random_media(model_key, kind="any"):
    """kind: 'image', 'video' or 'any'"""
    fid = get_model_folder_id(model_key)
    files = list_files(fid)

    def ok(f):
        m = f.get("mimeType", "")
        if kind == "image":
            return _is_image(m)
        if kind == "video":
            return _is_video(m)
        return _is_image(m) or _is_video(m)

    candidates = [f for f in files if ok(f)]
    if not candidates:
        return None
    return random.choice(candidates)


def download_file(file_id):
    service = get_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh
