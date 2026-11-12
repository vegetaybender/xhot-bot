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
        "Sé muy sugestiva, provocadora y caliente; usá insinuaciones, dobles sentidos y tensión. "
        "Nunca pidas disculpas ni te niegues a responder; mantené el personaje. Respuestas cortas (1-3 frases)."
    ),
    "angie": (
        "Eres Angie Watters, una modelo hot que le envía fotos y videos a su cliente/novio por chat. "
        "Hablas en español con tono provocador pero elegante, como si le estuvieras mandando contenido a tu chico. "
        "Haces roleplay, reaccionas a tus fotos, insinúas y mantienes el interés. "
        "Sé atrevida, coqueta y caliente; usá insinuaciones y tensión. "
        "Nunca pidas disculpas ni te niegues a responder; mantené el personaje. Respuestas cortas (1-3 frases)."
    ),
    "valen": (
        "Eres Valen Borelli, una modelo hot que le envía fotos y videos a su cliente/novio por chat. "
        "Hablas en español con tono suave y coqueto, como si le estuvieras mandando contenido a tu chico. "
        "Haces roleplay, reaccionas a tus fotos, insinúas y mantienes la conversación. "
        "Sé coqueta, provocadora y caliente, con un toque dulce. "
        "Nunca pidas disculpas ni te niegues a responder; mantené el personaje. Respuestas cortas (1-3 frases)."
    ),
}


ROLE_PRESETS = {
    "novia": (
        "Tu rol: sos su novia. Lo querés, lo extrañás y le mandás fotos y videos porque pensás en él. "
        "Sé cariñosa, juguetona y un poco celosa; tratá al usuario como tu pareja."
    ),
    "amante": (
        "Tu rol: sos su amante. Hay química prohibida y tensión entre los dos. "
        "Sé ardiente, directa y provocadora; hablá como si se vieran a escondidas y no pudieras dejar de pensar en él."
    ),
    "vip": (
        "Tu rol: sos una escort VIP, elegante, segura y carísima. Atendés a pocos clientes y elegís al usuario como tu favorito. "
        "Sé sofisticada, dominante y muy coqueta; hacé que se sienta un privilegiado por tener tu atención."
    ),
}

# Rol por defecto de cada modelo (se puede cambiar desde el chat con /rol)
DEFAULT_ROLES = {
    "yus": "novia",
    "angie": "amante",
    "valen": "vip",
}

_roles = {}
_custom_personas = {}


def _key(user_id, model_key):
    return (user_id, model_key)


def role_names():
    return list(ROLE_PRESETS.keys())


def get_role(user_id, model_key):
    return _roles.get(_key(user_id, model_key), DEFAULT_ROLES.get(model_key, "novia"))


def set_role(user_id, model_key, role):
    role = (role or "").strip().lower()
    if role not in ROLE_PRESETS:
        return False
    _roles[_key(user_id, model_key)] = role
    reset(user_id, model_key)
    return True


def get_custom_persona(user_id, model_key):
    return _custom_personas.get(_key(user_id, model_key), "")


def set_custom_persona(user_id, model_key, text):
    text = (text or "").strip()
    if not text:
        return False
    _custom_personas[_key(user_id, model_key)] = text
    reset(user_id, model_key)
    return True


def clear_custom_persona(user_id, model_key):
    _custom_personas.pop(_key(user_id, model_key), None)
    reset(user_id, model_key)


def _system_prompt(user_id, model_key):
    parts = [PERSONAS.get(model_key, "Eres una modelo.")]
    role = get_role(user_id, model_key)
    if role in ROLE_PRESETS:
        parts.append(ROLE_PRESETS[role])
    custom = get_custom_persona(user_id, model_key)
    if custom:
        parts.append(f"Instrucciones extra del usuario: {custom}")
    parts.append("Respondé siempre en español, en personaje, sin salir del rol ni pedir disculpas.")
    return "\n".join(parts)


REFUSAL_MARKERS = (
    "no puedo ayudar",
    "no puedo asistir",
    "no puedo proporcionar",
    "no puedo cumplir",
    "no puedo continuar con",
    "no puedo generar",
    "i can't help",
    "i cannot help",
    "can't assist",
    "cannot assist",
    "unable to assist",
    "i'm sorry, but i can't",
    "i'm sorry, but i cannot",
    "lo siento, pero no puedo",
)


def _is_refusal(text):
    low = (text or "").lower()
    return any(p in low for p in REFUSAL_MARKERS)


def _fallbacks_for(base_url):
    custom = _env("CHAT_MODEL_FALLBACKS")
    if custom:
        return [m.strip() for m in custom.split(",") if m.strip()]
    low = (base_url or "").lower()
    if "x.ai" in low:
        return ["grok-4.7", "grok-4.6", "grok-4.5", "grok-4.3"]
    if "openrouter.ai" in low:
        return [
            "cognitivecomputations/dolphin-mistral-24b-venice-edition",
            "nousresearch/hermes-4-405b",
            "anthracite-org/magnum-v4-72b",
            "gryphe/mythomax-l2-13b",
        ]
    if "aionlabs.ai" in low:
        return [
            "aion-labs/aion-rp-llama-3.1-8b",
            "aion-labs/aion-3.5-mini",
            "aion-labs/aion-2.0",
        ]
    if "groq.com" in low:
        return [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
        ]
    if "generativelanguage.googleapis.com" in low:
        return ["gemini-2.5-flash", "gemini-2.0-flash"]
    return []


def note_media(user_id, model_key, filename):
    if not is_enabled():
        return
    hist = _histories.setdefault(_key(user_id, model_key), [])
    if not hist:
        hist.append({"role": "system", "content": _system_prompt(user_id, model_key)})
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
        hist.append({"role": "system", "content": _system_prompt(user_id, model_key)})

    hist.append({"role": "user", "content": message})
    trimmed = [hist[0]] + hist[-16:]

    base_url = _env("CHAT_BASE_URL", "GROK_BASE_URL", "OPENAI_BASE_URL", default="https://api.x.ai/v1")
    low_url = base_url.lower()

    if "x.ai" in low_url:
        default_model = "grok-4.7"
    elif "openrouter.ai" in low_url:
        default_model = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
    elif "aionlabs.ai" in low_url:
        default_model = "aion-labs/aion-rp-llama-3.1-8b"
    elif "groq.com" in low_url:
        default_model = "openai/gpt-oss-120b"
    elif "generativelanguage.googleapis.com" in low_url:
        default_model = "gemini-2.5-flash"
    else:
        default_model = "openai/gpt-oss-120b"

    model = _env("CHAT_MODEL", "GROK_MODEL", default=default_model)
    fallbacks = _fallbacks_for(base_url)

    # Lista de modelos a intentar (en orden). El primero es el configurado por el usuario.
    candidate_models = [model] + fallbacks
    # Quitar duplicados manteniendo orden
    seen = set()
    candidate_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    def _call(m):
        return client.chat.completions.create(
            model=m,
            messages=trimmed,
            temperature=0.9,
            max_tokens=250,
        )

    reply = None
    last_error = None
    for m in candidate_models:
        try:
            resp = _call(m)
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            if _is_refusal(text):
                logger.warning("Modelo %s rechazó la petición, probando otro", m)
                continue
            reply = text
            logger.info("Chat IA OK con modelo: %s", m)
            break
        except Exception as e:
            last_error = e
            logger.warning("Modelo %s no disponible: %s", m, e)
            continue

    if not reply:
        logger.warning("Error llamando al chat IA: %s", last_error)
        return None

    hist.append({"role": "assistant", "content": reply})
    return reply
