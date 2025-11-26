from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ---------------- ENV VARIABLES ----------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "c3802e9e6d0cabfd189dde96a6f58fae")

# ---------------- CREATOR MESSAGE ----------------
CREATOR_MESSAGE = (
    "I was developed for Lovely Professional University (LPU) "
    "and created by Vennela Barnana."
)

# ================================================================
#  WEATHER FUNCTIONS
# ================================================================
def correct_city_name(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_API_KEY}"
        r = requests.get(url, timeout=7).json()
        if not r:
            return None
        return r[0]["name"]
    except:
        return None


def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=7).json()
        if r.get("cod") != 200:
            return "❌ City not found. Try another city."

        temp = r["main"]["temp"]
        feels = r["main"]["feels_like"]
        humidity = r["main"]["humidity"]
        desc = r["weather"][0]["description"].title()

        return (
            f"🌦 *Weather in {city.title()}*\n"
            f"🌡 Temperature: {temp}°C\n"
            f"🤗 Feels Like: {feels}°C\n"
            f"💧 Humidity: {humidity}%\n"
            f"🌥 Condition: {desc}"
        )
    except:
        return "⚠️ Weather service error."


# ================================================================
#  LOAD ALL SECTION FILES
# ================================================================
def load_sections():
    sections_folder = "sections"
    data = {}

    if not os.path.exists(sections_folder):
        return data

    for filename in os.listdir(sections_folder):
        if filename.endswith(".txt"):
            with open(os.path.join(sections_folder, filename), "r", encoding="utf-8") as f:
                key = filename.replace(".txt", "")
                data[key] = f.read().strip()

    return data


SECTIONS = load_sections()


# ================================================================
#  FIND BEST ANSWER IN SECTION FILES
# ================================================================
def find_answer_in_sections(text):
    t = text.lower()

    for key, content in SECTIONS.items():
        if key.replace("_", " ") in t:
            return content

    # keyword scanning
    for key, content in SECTIONS.items():
        if any(word in t for word in key.split("_")):
            return content

    return None


# ================================================================
#  RULE-BASED SYSTEM (forces LPU answers to come from data)
# ================================================================
def rule_based(text):
    t = text.lower()

    # Developer response rule
    if any(k in t for k in [
        "who built", "who made", "who created", "who developed",
        "developer", "founder", "your creator", "your developer"
    ]):
        return CREATOR_MESSAGE

    # All LPU-related keywords → must use section data
    lpu_keywords = [
        "attendance", "soa", "hostel", "leave", "night out", "gate pass",
        "mess", "food", "parking", "rfid", "security", "entry", "exit",
        "visitor", "rms", "relationship management", "discipline",
        "library", "medical", "placements", "transport", "wifi",
        "network", "exam", "reappear", "cgpa", "fee", "fine", "rules",
        "timings", "id card", "uniform", "dress code", "warden",
        "otp", "check in", "check out", "day leave", "night leave"
    ]

    if any(k in t for k in lpu_keywords):
        return None  # means: MUST search data files

    return "AI"  # non-LPU question → AI allowed


# ================================================================
#  AI FALLBACK
# ================================================================
def ai_reply(user_message):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are an assistant. For LPU questions, use: 'Please ask LPU-related questions only.'\n"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.4
    }

    try:
        r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=15).json()
        return r["choices"][0]["message"]["content"]
    except:
        return "⚠️ AI engine busy. Try again."


# ================================================================
#  SEND MESSAGE TO WHATSAPP
# ================================================================
def send_message(to, text):
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}

    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except:
        pass


# ================================================================
#  WEBHOOK VERIFY
# ================================================================
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params["hub.challenge"])
    return "Invalid verify token"


# ================================================================
#  MAIN WEBHOOK HANDLER
# ================================================================
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message["text"]["body"].strip()
    except:
        return {"status": "ignored"}

    # ---------------------------------------------------------
    # WELCOME message
    # ---------------------------------------------------------
    if text.lower() in ["hi", "hello", "hey", "menu", "start"]:
        send_message(
            sender,
            "👋 Hello! I am your *LPU Assistant Bot*.\n"
            "Ask anything about LPU rules, attendance, hostel, leave, security, parking, mess, RFID, RMS, etc.\n\n"
            "You can also ask:\n• Time now\n• Weather city\n• Weather at LPU\n"
        )
        return {"status": "ok"}

    # ---------------------------------------------------------
    # LIVE TIME
    # ---------------------------------------------------------
    if text.lower() in ["time", "time now", "what is the time"]:
        now = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
        send_message(sender, f"⏰ Current time: {now.strftime('%I:%M %p')}")
        return {"status": "ok"}

    # ---------------------------------------------------------
    # LIVE WEATHER
    # ---------------------------------------------------------
    if "weather" in text.lower() or "climate" in text.lower():
        if "lpu" in text.lower():
            corrected = correct_city_name("phagwara")
            send_message(sender, get_weather(corrected))
            return {"status": "ok"}

        cleaned = text.lower().replace("weather", "").replace("in", "").replace("at", "").strip()
        corrected = correct_city_name(cleaned)
        if not corrected:
            send_message(sender, "⚠️ City not recognized.")
            return {"status": "ok"}

        send_message(sender, get_weather(corrected))
        return {"status": "ok"}

    # ---------------------------------------------------------
    # RULE BASED SYSTEM
    # ---------------------------------------------------------
    rb = rule_based(text)

    # Must answer from data files
    if rb is None:
        ans = find_answer_in_sections(text)
        if ans:
            send_message(sender, ans)
            return {"status": "ok"}

        # If nothing found even in data → fallback AI
        reply = ai_reply(text)
        send_message(sender, reply)
        return {"status": "ok"}

    # Direct reply (e.g., creator)
    if rb != "AI":
        send_message(sender, rb)
        return {"status": "ok"}

    # Non-LPU → AI mode
    reply = ai_reply(text)
    send_message(sender, reply)
    return {"status": "ok"}
