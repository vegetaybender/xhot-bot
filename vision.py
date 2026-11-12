import base64
import io
import logging
import os
import time

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False

try:
    from PIL import Image, ImageOps
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False

_client = None
_vision_cache = {}

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VISION_SIDE = 640
MAX_CACHE_ITEMS = 500
TOTAL_VISION_TIMEOUT = 12.0
REQUEST_TIMEOUT = 8.0

# Modelos de visión en orden de preferencia. Google retira modelos viejos para
# cuentas nuevas y a veces los más nuevos están saturados (503).
DEFAULT_VISION_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
)

# Modelos que ya no están disponibles para cuentas nuevas.
RETIRED_VISION_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
}


def _env(*names, default=""):
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return default


def _normalize_model(name):
    name = (name or "").strip()
    if name.startswith("models/"):
        name = name[len("models/"):]
    return name


def _model_candidates():
    configured = _normalize_model(_env("VISION_MODEL", default=""))
    candidates = []
    if configured and configured not in RETIRED_VISION_MODELS:
        candidates.append(configured)
    for model in DEFAULT_VISION_MODELS:
        model = _normalize_model(model)
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def is_enabled():
    return _OPENAI_AVAILABLE and bool(_env("VISION_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"))


def get_client():
    global _client
    if _client is None and is_enabled():
        _client = OpenAI(
            api_key=_env("VISION_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
            base_url=_env(
                "VISION_BASE_URL",
                default="https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            timeout=REQUEST_TIMEOUT,
            max_retries=0,
        )
    return _client


def _prepare_image(data, mime):
    """Achica la imagen para que Gemini la procese más rápido."""
    if not data:
        return None, mime

    if not _PIL_AVAILABLE or not (mime or "").lower().startswith("image/"):
        return data, mime

    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((MAX_VISION_SIDE, MAX_VISION_SIDE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception as e:
        logger.debug("No pude redimensionar la imagen: %s", e)
        return data, mime


def _is_transient(msg):
    low = (msg or "").lower()
    markers = (
        "404",
        "not_found",
        "no longer available",
        "503",
        "unavailable",
        "high demand",
        "overloaded",
        "429",
        "too many requests",
        "500",
        "502",
        "504",
        "timed out",
        "timeout",
    )
    return any(m in low for m in markers)


def _is_auth_error(msg):
    low = (msg or "").lower()
    markers = (
        "401",
        "403",
        "invalid api key",
        "api key not valid",
        "permission_denied",
        "unauthenticated",
    )
    return any(m in low for m in markers)


def describe_images(images, kind="foto", cache_key=None):
    """images: lista de tuplas (bytes, mime). Devuelve una descripción corta o None."""
    if cache_key is not None:
        cached = _vision_cache.get(cache_key)
        if cached:
            logger.info("Descripción de %s desde caché: %s", kind, cached)
            return cached

    if not is_enabled() or not images:
        return None

    client = get_client()
    if client is None:
        return None

    if kind == "album":
        prompt = (
            "Describí el conjunto de fotos en una sola frase de máximo 18 palabras, en español rioplatense. "
            "Sé muy concreto: lugar, ropa y colores, poses, expresión y qué se ve. "
            "No uses generalidades ni inventes."
        )
    else:
        prompt = (
            "Describí la foto en una sola frase de máximo 15 palabras, en español rioplatense. "
            "Sé muy concreto: lugar, ropa y colores, pose, expresión y qué se ve. "
            "No uses generalidades ni inventes. "
            "Ejemplo: cama, sábana blanca, lencería negra, escote, mirando a cámara."
        )

    content = [{"type": "text", "text": prompt}]
    for data, mime in images[:3]:
        data, mime = _prepare_image(data, mime)
        if not data or len(data) > MAX_IMAGE_BYTES:
            continue
        b64 = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime or 'image/jpeg'};base64,{b64}"},
            }
        )

    if len(content) == 1:
        return None

    deadline = time.monotonic() + TOTAL_VISION_TIMEOUT
    for model in _model_candidates():
        remaining = deadline - time.monotonic()
        if remaining <= 1.0:
            break
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=70,
                temperature=0.4,
                timeout=min(REQUEST_TIMEOUT, remaining),
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            low = text.lower()
            if any(
                p in low
                for p in (
                    "no puedo",
                    "i can't",
                    "i cannot",
                    "can't assist",
                    "cannot assist",
                    "lo siento",
                    "unable to",
                )
            ):
                logger.warning("Visión rechazó la descripción con %s: %s", model, text)
                return None
            if cache_key is not None:
                _vision_cache[cache_key] = text
                if len(_vision_cache) > MAX_CACHE_ITEMS:
                    _vision_cache.pop(next(iter(_vision_cache)))
            logger.info("Descripción de %s con %s: %s", kind, model, text)
            return text
        except Exception as e:
            msg = str(e)
            logger.warning("Error de visión con %s: %s", model, e)
            if _is_auth_error(msg):
                break
            if _is_transient(msg):
                continue
            break

    return None
