from fastapi import FastAPI, Request
import requests
import os
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# --------------------------
# ENV VARIABLES
# --------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_WEATHER = "https://api.open-meteo.com/v1/forecast"

# --------------------------
# LOAD KNOWLEDGE BASE
# --------------------------
def load_knowledge_base():
    kb = {}
    current = None
    if not os.path.exists("lpu_knowledge.txt"):
        logging.warning("knowledge base missing")
        return kb

    with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().isupper():
                current = line.strip()
                kb[current] = []
            elif current:
                kb[current].append(line.rstrip())

    for k in kb:
        kb[k] = "\n".join(kb[k])
    return kb

KB = load_knowledge_base()

# --------------------------
# SAFETY FILTER
# --------------------------
BLOCK_LIST = ["sex", "porn", "fuck", "nude", "hack", "crime", "bomb", "kill"]

def is_unsafe(text):
    t = text.lower()
    for b in BLOCK_LIST:
        if b in t:
            return True
    return False

# --------------------------
# INTENT DETECTOR (FUZZY)
# --------------------------
INTENT = {
    "ATTENDANCE": ["attendance", "attnd", "75%", "soa", "shortage"],
    "HOSTEL": ["hostel", "warden", "night leave", "intime", "leave pass"],
    "EXAM": ["exam", "reappear", "umc", "admit card", "paper"],
    "CGPA": ["cgpa", "grade", "gpa"],
    "RMS": ["rms", "complaint", "ticket"],
    "MEDICAL": ["medical", "hospital", "uni health"],
    "DRESS": ["dress code", "uniform"],
    "MESS": ["mess", "dining"],
    "PLACEMENT": ["placement", "company"],
    "CREATOR": ["who created you", "developer", "maker", "vennela"],
    "WEATHER": ["weather", "temperature", "climate"],
    "TIME": ["time", "date", "day"]
}

def detect_intent(text):
    t = text.lower()
    for key, words in INTENT.items():
        for w in words:
            if w in t:
                return key
    return None

# --------------------------
# GEOCODING (ANY CITY/VILLAGE)
# --------------------------
def geocode_place(place):
    try:
        r = requests.get(OPEN_METEO_GEOCODE, params={"name": place, "count": 1})
        data = r.json()
        if "results" not in data or not data["results"]:
            return None
        res = data["results"][0]
        return {
            "name": res["name"],
            "lat": res["latitude"],
            "lon": res["longitude"],
            "country": res.get("country", ""),
            "tz": res.get("timezone", "")
        }
    except:
        return None

# --------------------------
# WEATHER API
# --------------------------
def get_weather(place):
    geo = geocode_place(place)
    if not geo:
        return None
    try:
        r = requests.get(OPEN_METEO_WEATHER, params={
            "latitude": geo["lat"],
            "longitude": geo["lon"],
            "current_weather": True,
            "timezone": "auto"
        })
        w = r.json().get("current_weather")
        if not w:
            return None
        return (
            f"🌤 Weather in {geo['name']}, {geo['country']}:\n"
            f"Temperature: {w['temperature']}°C\n"
            f"Wind: {w['windspeed']} km/h\n"
            f"Time: {w['time']}"
        )
    except:
        return None

# --------------------------
# TIME & DATE
# --------------------------
def get_time(place):
    geo = geocode_place(place)
    if not geo or not geo["tz"]:
        return None
    try:
        now = datetime.now(ZoneInfo(geo["tz"]))
        return (
            f"⏰ Time in {geo['name']}, {geo['country']}:\n"
            f"{now.strftime('%I:%M %p, %A, %d %B %Y')}"
        )
    except:
        return None

# --------------------------
# KNOWLEDGE BASE LOOKUP
# --------------------------
def kb_lookup(text):
    t = text.lower()
    for section, content in KB.items():
        if section.lower() in t:
            return content
    return None

# --------------------------
# GROQ AI FALLBACK
# --------------------------
def ai_reply(msg):
    if not GROQ_API_KEY:
        return "My AI engine is not configured."

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content":
                "You are a friendly LPU assistant. "
                "Answer LPU questions from knowledge base. "
                "Answer education, UPSC, GK, science, history questions using your intelligence. "
                "Do NOT answer personal, illegal, explicit or harmful questions."
            },
            {"role": "user", "content": msg}
        ],
        "temperature": 0.3
    }

    r = requests.post(GROQ_URL, json=payload, headers=headers)
    data = r.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    return "AI error, please try again."

# --------------------------
# MAIN REPLY LOGIC
# --------------------------
def build_reply(text):
    t = text.lower()

    # Safety filter
    if is_unsafe(t):
        return "❌ Sorry, I can help only with LPU info, academics, GK, UPSC and learning."

    # Creator / Developer
    if "who created you" in t or "developer" in t or "vennela" in t:
        return (
            "I was created for Lovely Professional University (LPU) and developed by the Founders of Dream Sphere.\n\n"
            "About Vennela Barnana:\n"
            "• Author of “Unstoppable in 7 Days”\n"
            "• Developer of AI-based Chatbots\n"
            "• Studying at Lovely Professional University\n"
            "• From Srikakulam, Andhra Pradesh\n"
        )

    # Weather
    if any(w in t for w in ["weather", "temperature", "climate"]):
        place = t.replace("weather in", "").replace("climate in", "").strip()
        w = get_weather(place)
        return w or "I couldn't get weather for that place."

    # Time
    if "time" in t or "date" in t or "day" in t:
        place = t.replace("time in", "").replace("date in", "").replace("day in", "").strip()
        tm = get_time(place)
        return tm or "I couldn't get the local time for that city."

    # Knowledge base
    kb = kb_lookup(t)
    if kb:
        return "📘 LPU Information:\n\n" + kb

    # Fallback to AI
    return ai_reply(text)

# --------------------------
# WHATSAPP SEND MSG
# --------------------------
def send_message(to, body):
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": body}
    }
    requests.post(url, json=data, headers=headers)

# --------------------------
# WEBHOOKS
# --------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params["hub.challenge"])
    return "Invalid Token"

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        text = msg["text"]["body"]
        sender = msg["from"]
        reply = build_reply(text)
        send_message(sender, reply)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    return {"status": "ok"}
