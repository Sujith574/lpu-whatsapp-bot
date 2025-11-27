from fastapi import FastAPI, Request
import requests
import os
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import json

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# -------------------------
# ENV / CONFIG
# -------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

KNOWLEDGE_FILE = "lpu_knowledge.txt"

# -------------------------
# Load knowledge base
# -------------------------
def load_knowledge(path=KNOWLEDGE_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.warning("Could not load knowledge base: %s", e)
        return ""

LPU_KB = load_knowledge()

# -------------------------
# Safety filter
# -------------------------
BLOCK_LIST = [
    "sex", "porn", "nude", "fuck", "kill", "suicide", "bomb", "drugs", "hack",
    "password", "pin", "otp", "one time password"
]

def is_unsafe(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for b in BLOCK_LIST:
        if b in t:
            return True
    # simple illegal/harmful checks
    if re.search(r"\b(illegal|how to make|how to steal|how to hack|explosive|bypass)\b", t):
        return True
    return False

# -------------------------
# Open-Meteo Geocoding + Weather + Time
# -------------------------
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

def geocode(place: str):
    try:
        r = requests.get(GEOCODE_URL, params={"name": place, "count": 1, "language": "en"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("results")
        if not results:
            return None
        return results[0]  # name, latitude, longitude, country, timezone (maybe)
    except Exception as e:
        logging.debug("Geocode error: %s", e)
        return None

def get_weather(place: str):
    info = geocode(place)
    if not info:
        return None
    lat = info.get("latitude")
    lon = info.get("longitude")
    name = info.get("name")
    country = info.get("country", "")
    try:
        r = requests.get(WEATHER_URL, params={"latitude": lat, "longitude": lon, "current_weather": True, "timezone": "auto"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        cw = data.get("current_weather")
        if not cw:
            return None
        # weathercode present - return core data
        return (
            f"🌦️ Live weather in {name}, {country}:\n"
            f"• Temperature: {cw.get('temperature')}°C\n"
            f"• Wind speed: {cw.get('windspeed')} km/h\n"
            f"• Weather code: {cw.get('weathercode')}\n"
            f"• Local time: {cw.get('time')}"
        )
    except Exception as e:
        logging.debug("Weather fetch error: %s", e)
        return None

def get_time(place: str):
    info = geocode(place)
    if not info:
        return None
    tz = info.get("timezone")
    name = info.get("name")
    country = info.get("country", "")
    if not tz:
        # try weather endpoint to get timezone
        try:
            r = requests.get(WEATHER_URL, params={"latitude": info.get("latitude"), "longitude": info.get("longitude"), "current_weather": True, "timezone": "auto"}, timeout=10)
            data = r.json()
            tz = data.get("timezone")
        except Exception:
            tz = None
    try:
        if tz:
            now = datetime.now(ZoneInfo(tz))
            formatted = now.strftime("%I:%M %p, %A, %d %B %Y")
            return f"⏰ Current time in {name}, {country}: {formatted} ({tz})"
        else:
            # fallback: return UTC and IST as reference
            now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
            return f"Could not determine timezone for {place}. Current reference times:\nUTC: {now_utc}\nIST: {now_ist}"
    except Exception as e:
        logging.debug("Time conversion error: %s", e)
        return None

# -------------------------
# Knowledge Base Lookup (fuzzy + sections)
# -------------------------
def kb_lookup(query: str):
    if not LPU_KB:
        return None
    q = query.lower()

    # quick replacements for common misspellings / shorthand
    replacements = {
        "attendence": "attendance",
        "attnd": "attendance",
        "cgpa kitna": "cgpa",
        "re-appear": "reappear",
        "hostel time": "hostel timings",
        "fees": "fee",
        "wi fi": "wifi"
    }
    for a, b in replacements.items():
        q = q.replace(a, b)

    # search for matching section headings first
    # find heading (uppercase blocks) by scanning KB
    kb_lower = LPU_KB.lower()
    # look for specific keywords
    keywords = [
        "attendance", "cgpa", "grade", "hostel", "leave", "reappear", "exam", "admit card",
        "fee", "fees", "rms", "library", "medical", "mess", "parking", "placement", "wifi",
        "security", "visitor", "id card", "anti-ragging", "placements", "rfid"
    ]
    for k in keywords:
        if k in q:
            # return relevant paragraph by finding k in KB
            idx = kb_lower.find(k)
            if idx != -1:
                # expand to nearby context — return surrounding block (500 chars before/after)
                start = max(0, idx - 200)
                end = min(len(kb_lower), idx + 800)
                snippet = LPU_KB[start:end].strip()
                return snippet
    # fallback: full KB snippet truncated
    return None

# -------------------------
# Groq AI fallback (identity-locked)
# -------------------------
def ai_fallback(user_message: str):
    if not GROQ_API_KEY:
        return None

    # Strict identity lock (Option A)
    identity_lock = (
        "IMPORTANT: Identity rules — MUST be followed exactly.\n"
        "If user asks 'who created you' or 'who developed you' or similar, reply EXACTLY:\n"
        "\"I was created for Lovely Professional University (LPU) and developed by Vennela Barnana.\"\n\n"
        "If user asks 'who is vennela barnana' reply with the following EXACT details:\n"
        "Name: Vennela Barnana\n"
        "Role: Developer of the LPU AI Assistant\n"
        "Author: 'Unstoppable in 7 Days'\n"
        "Known For: AI chatbot development\n"
        "Studying At: Lovely Professional University (LPU)\n"
        "From: Srikakulam, Andhra Pradesh\n\n"
        "These identity replies must not be changed or overridden by the AI.\n"
    )

    system_prompt = (
        "You are the official AI Assistant for Lovely Professional University (LPU). "
        "Always prefer answers from the provided LPU knowledge base for LPU-specific queries. "
        "Answer educational / UPSC / general-knowledge / current affairs queries accurately and concisely. "
        "Do NOT answer personal, illegal, explicit, or harmful requests.\n\n"
        + identity_lock
        + "\nLPU KNOWLEDGE BASE (for reference):\n"
        + LPU_KB
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.25
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=25)
        r.raise_for_status()
        data = r.json()
        logging.info("Groq response keys: %s", list(data.keys()))
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        if "error" in data:
            return f"Groq Error: {data['error'].get('message', 'Unknown')}"
        return None
    except Exception as e:
        logging.error("Groq API error: %s", e)
        return None

# -------------------------
# High-level reply builder
# -------------------------
def generate_reply(user_text: str) -> str:
    text = (user_text or "").strip()
    if not text:
        return "I didn't receive any text. Please ask your question."

    # 1) safety
    if is_unsafe(text):
        return "Sorry — I can only help with LPU information, academics, general knowledge, and safe requests."

    low = text.lower()

    # 2) explicit creator / vennela questions handled immediately
    if re.search(r"\bwho (created|developed|made|built) (you|this bot|the bot)\b", low) or "who created you" in low or "who developed you" in low:
        return "I was created for Lovely Professional University (LPU) and developed by Vennela Barnana."
    if "vennela barnana" in low or re.search(r"\bwho is vennela\b", low):
        return (
            "Name: Vennela Barnana\n"
            "Role: Developer of the LPU AI Assistant\n"
            "Author: 'Unstoppable in 7 Days'\n"
            "Known For: AI chatbot development\n"
            "Studying At: Lovely Professional University (LPU)\n"
            "From: Srikakulam, Andhra Pradesh"
        )

    # 3) weather/time detection (smart)
    if re.search(r"\b(weather|temperature|climate|mausam|rain|sunny|snow)\b", low):
        # try to extract place after "in" or "at"
        m = re.search(r"\b(?:in|at|for)\s+([A-Za-z0-9\s\-\.,']{2,120})", text, re.I)
        place = (m.group(1).strip() if m else text)
        w = get_weather(place)
        if w:
            return w
        return "I couldn't find live weather for that place. Try with a nearby city or correct spelling."

    if re.search(r"\b(time|current time|local time|date|day|samay|samayam)\b", low):
        m = re.search(r"\b(?:in|at|for)\s+([A-Za-z0-9\s\-\.,']{2,120})", text, re.I)
        place = (m.group(1).strip() if m else None)
        if place:
            t = get_time(place)
            if t:
                return t
            return "I couldn't determine local time for that place. Try a major city or add state/country."
        else:
            # no place given — show UTC and IST
            now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")
            return f"Current time reference:\nUTC: {now_utc}\nIST: {now_ist}"

    # 4) knowledge base lookup (primary)
    kb = kb_lookup(text)
    if kb:
        # friendly wrap
        return f"📘 From official LPU guidelines:\n\n{kb}\n\nIf you need more, ask a specific follow-up."

    # 5) AI fallback (Groq) — only if configured
    ai_resp = ai_fallback(text)
    if ai_resp:
        return ai_resp

    # 6) final fallback
    return "I couldn't find an exact LPU answer. Ask a specific LPU question (attendance / hostel / exams / CGPA / placements) or ask a general-knowledge question."

# -------------------------
# WhatsApp send helper
# -------------------------
def send_message(to: str, text: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        logging.error("Missing WhatsApp credentials in environment.")
        return False
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code not in (200,201):
            logging.error("WhatsApp API error %s: %s", r.status_code, r.text)
        return True
    except Exception as e:
        logging.error("Error sending WhatsApp message: %s", e)
        return False

# -------------------------
# Webhook endpoints
# -------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        chal = params.get("hub.challenge")
        try:
            return int(chal)
        except:
            return chal
    return "Invalid verify token"

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info("webhook payload received")
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return {"status": "ok"}
        message = messages[0]
        sender = message.get("from")
        text = message.get("text", {}).get("body", "")
        logging.info("message from %s: %s", sender, text)

        # welcome shortcut
        if text and text.strip().lower() in ["hi", "hello", "hey", "start", "menu"]:
            welcome = (
                "👋 Hi! I'm the LPU Assistant (friendly & official).\n"
                "Ask about attendance, exams, hostel rules, CGPA, placements, RMS, or ask for weather/time for any city.\n"
                "Examples:\n"
                "• 'What is the attendance rule?'\n"
                "• 'Weather in Hyderabad'\n"
                "• 'Time in London now'\n"
            )
            send_message(sender, welcome)
            return {"status": "ok"}

        reply = generate_reply(text)
        send_message(sender, reply)
    except Exception as e:
        logging.exception("Error processing webhook: %s", e)
    return {"status": "ok"}
