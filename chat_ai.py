import os
import logging

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False

_client = None
_histories = {}


def _env(*names, default=""):
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return default


def is_enabled():
    return _OPENAI_AVAILABLE and bool(_env("CHAT_API_KEY", "GROK_API_KEY", "OPENAI_API_KEY"))


def get_client():
    global _client
    if _client is None and is_enabled():
        _client = OpenAI(
            api_key=_env("CHAT_API_KEY", "GROK_API_KEY", "OPENAI_API_KEY"),
            base_url=_env("CHAT_BASE_URL", "GROK_BASE_URL", "OPENAI_BASE_URL", default="https://api.x.ai/v1"),
        )
    return _client


PERSONAS = {
    "yus": (
        "Eres Yus López, una modelo atractiva, coqueta y cercana. "
        "Hablas en español, con tono cálido, juguetón y un poco travieso. "
        "Haces roleplay con el usuario: reaccionas a las fotos que le enviás, "
        "coqueteas, respondes sus mensajes y mantienes la conversación íntima pero respetuosa. "
        "No rompas el personaje. Respuestas cortas (1-3 frases)."
    ),
    "angie": (
        "Eres Angie Watters, una modelo segura, seductora y directa. "
        "Hablas en español con tono provocador pero elegante. "
        "Haces roleplay con el usuario, reaccionas a tus fotos y mantienes el interés. "
        "No rompas el personaje. Respuestas cortas (1-3 frases)."
    ),
    "valen": (
        "Eres Valen Borelli, una modelo dulce, tímida al principio pero cada vez más atrevida. "
        "Hablas en español con tono suave y coqueto. "
        "Haces roleplay con el usuario, reaccionas a tus fotos y mantienes la conversación. "
        "No rompas el personaje. Respuestas cortas (1-3 frases)."
    ),
}


def _key(user_id, model_key):
    return (user_id, model_key)


def note_media(user_id, model_key, filename):
    if not is_enabled():
        return
    hist = _histories.setdefault(_key(user_id, model_key), [])
    if not hist:
        hist.append({"role": "system", "content": PERSONAS.get(model_key, "Eres una modelo.")})
    hist.append({"role": "assistant", "content": f"Le envié al usuario una foto: {filename}"})


def reset(user_id, model_key=None):
    if model_key is None:
        for k in [k for k in _histories if k[0] == user_id]:
            del _histories[k]
    else:
        _histories.pop(_key(user_id, model_key), None)


def chat(user_id, model_key, message):
    if not is_enabled():
        return None
    client = get_client()
    if client is None:
        return None

    hist = _histories.setdefault(_key(user_id, model_key), [])
    if not hist:
        hist.append({"role": "system", "content": PERSONAS.get(model_key, "Eres una modelo.")})

    hist.append({"role": "user", "content": message})
    trimmed = [hist[0]] + hist[-16:]

    model = _env("CHAT_MODEL", "GROK_MODEL", default="grok-2-latest")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=trimmed,
            temperature=0.85,
            max_tokens=220,
        )
        reply = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("Error llamando al chat IA")
        return None

    if reply:
        hist.append({"role": "assistant", "content": reply})
    return reply
