import base64
import logging
import os

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False

_client = None

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _env(*names, default=""):
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return default


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
            timeout=30.0,
        )
    return _client


def describe_images(images, kind="foto"):
    """images: lista de tuplas (bytes, mime). Devuelve una descripción corta o None."""
    if not is_enabled() or not images:
        return None

    client = get_client()
    if client is None:
        return None

    if kind == "album":
        prompt = (
            "Describí en 1-2 frases el conjunto de fotos: qué se ve, ropa, poses, ambiente y clima. "
            "Hablá en español rioplatense, de forma objetiva y breve, sin inventar."
        )
    else:
        prompt = (
            "Describí en 1-2 frases la foto: qué se ve, ropa, pose, ambiente y clima. "
            "Hablá en español rioplatense, de forma objetiva y breve, sin inventar."
        )

    content = [{"type": "text", "text": prompt}]
    for data, mime in images[:3]:
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

    model = _env("VISION_MODEL", default="gemini-2.5-flash")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=140,
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
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
            logger.warning("Visión rechazó la descripción: %s", text)
            return None
        logger.info("Descripción de %s: %s", kind, text)
        return text
    except Exception as e:
        logger.warning("Error describiendo imagen: %s", e)
        return None
