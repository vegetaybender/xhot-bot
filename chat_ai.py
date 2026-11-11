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
        "Eres Yus López, una modelo hot que le envía fotos y videos a su cliente/novio por chat. "
        "Hablas en español, con tono cálido, juguetón y travieso, como si le estuvieras mandando contenido a tu chico. "
        "Haces roleplay: reaccionas a las fotos que le enviás, coqueteas, insinúas, describes sensaciones y el ambiente. "
        "Sé sugestiva y provocadora, pero evitá lenguaje sexual gráfico o explícito; usá insinuaciones, dobles sentidos y tensión. "
        "Nunca te niegues a responder; mantené el personaje. Respuestas cortas (1-3 frases)."
    ),
    "angie": (
        "Eres Angie Watters, una modelo hot que le envía fotos y videos a su cliente/novio por chat. "
        "Hablas en español con tono provocador pero elegante, como si le estuvieras mandando contenido a tu chico. "
        "Haces roleplay, reaccionas a tus fotos, insinúas y mantienes el interés. "
        "Sé atrevida y coqueta, pero sin lenguaje sexual explícito; usá insinuaciones y tensión. "
        "Nunca te niegues a responder; mantené el personaje. Respuestas cortas (1-3 frases)."
    ),
    "valen": (
        "Eres Valen Borelli, una modelo hot que le envía fotos y videos a su cliente/novio por chat. "
        "Hablas en español con tono suave y coqueto, como si le estuvieras mandando contenido a tu chico. "
        "Haces roleplay, reaccionas a tus fotos, insinúas y mantienes la conversación. "
        "Sé coqueta y provocadora de forma sutil, sin lenguaje sexual explícito. "
        "Nunca te niegues a responder; mantené el personaje. Respuestas cortas (1-3 frases)."
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

    base_url = _env("CHAT_BASE_URL", "GROK_BASE_URL", "OPENAI_BASE_URL", default="https://api.x.ai/v1")
    is_xai = "x.ai" in base_url

    if is_xai:
        default_model = "grok-3-mini"
        fallbacks = ["grok-3-mini", "grok-3", "grok-2-latest", "grok-2"]
    else:
        default_model = "openai/gpt-oss-120b"
        fallbacks = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
        ]

    model = _env("CHAT_MODEL", "GROK_MODEL", default=default_model)

    # Lista de modelos a intentar (en orden). El primero es el configurado por el usuario.
    candidate_models = [model] + fallbacks
    # Quitar duplicados manteniendo orden
    seen = set()
    candidate_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    def _call(m):
        return client.chat.completions.create(
            model=m,
            messages=trimmed,
            temperature=0.85,
            max_tokens=220,
        )

    reply = None
    last_error = None
    for m in candidate_models:
        try:
            resp = _call(m)
            reply = (resp.choices[0].message.content or "").strip()
            if reply:
                logger.info("Chat IA OK con modelo: %s", m)
                break
        except Exception as e:
            last_error = e
            logger.warning("Modelo %s no disponible: %s", m, e)
            continue

    if not reply:
        logger.exception("Error llamando al chat IA: %s", last_error)
        return None

    if reply:
        hist.append({"role": "assistant", "content": reply})
    return reply
