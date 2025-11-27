from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz
import re

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ---------------- ENV ----------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"

CREATOR_MESSAGE = "I was specially designed only for Lovely Professional University (LPU). Developed by Vennela Barnana."
NON_LPU_REPLY = "I can answer only educational or LPU-related questions."

DATA_FILE = "data.txt"

# ---------------- LOAD DATA ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        logging.warning("data.txt missing!")
        return {}

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    section_pattern = re.compile(r"^[A-Z0-9 \\-]{3,80}$")

    sections = {}
    key = "general"
    buffer = []

    for line in lines:
        stripped = line.strip()
        if section_pattern.match(stripped):
            if buffer:
                sections[key] = "\n".join(buffer).strip()
            key = stripped.lower().replace(" ", "_")
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        sections[key] = "\n".join(buffer).strip()

    return sections

SECTIONS = load_data()

# ---------------- WEATHER ----------------
OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY", "c3802e9e6d0cabfd189dde96a6f58fae")

def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_KEY}&units=metric"
        r = requests.get(url).json()
        if r.get("cod") != 200:
            return "City not found."

        temp = r["main"]["temp"]
        feels = r["main"]["feels_like"]
        desc = r["weather"][0]["description"].title()

        return f"Weather in {city.title()}:\nTemp: {temp}°C\nFeels Like: {feels}°C\nCondition: {desc}"
    except:
        return "Weather service unavailable."

# ---------------- SEARCH ENGINE ----------------
keyword_map = {
    "attendance": "attendance_rules",
    "leave": "hostel_leave_rules",
    "hostel": "hostel_rules",
    "mess": "mess_rules",
    "exam": "exam_rules",
    "id card": "id_card_rules",
    "rfid": "rfid_traffic_rules",
    "medical": "medical_rules",
    "security": "security_safety_rules",
    "wifi": "wifi_internet_rules",
    "library": "library_rules",
    "rms": "rms_system",
    "placement": "placement_rules",
    "parking": "parking_rules"
}

def find_section(text):
    t = text.lower()
    for word, key in keyword_map.items():
        if word in t and key in SECTIONS:
            return SECTIONS[key]
    return None

# ---------------- EDUCATIONAL CHECK ----------------
edu_words = [
    "attendance","exam","hostel","leave","cgpa","ums","rms","semester","course",
    "mess","warden","wifi","security","placement","library","medical","rfid"
]

def is_edu(text):
    t = text.lower()
    return any(x in t for x in edu_words)

# ---------------- AI FALLBACK ----------------
def ai_fallback(text):
    if not GROQ_API_KEY:
        return "AI backend offline."

    if not is_edu(text):
        return NON_LPU_REPLY

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Give short, clear replies for LPU educational questions."},
            {"role": "user", "content": text}
        ]
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers).json()
        return r["choices"][0]["message"]["content"]
    except:
        return "AI service unavailable."

# ---------------- SEND MESSAGE ----------------
def send_message(to, body):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": body}}

    try:
        requests.post(url, json=payload)
    except:
        pass

# ---------------- VERIFY WEBHOOK ----------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid token"

# ---------------- MAIN WEBHOOK ----------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = msg["from"]
        text = msg["text"]["body"].strip()
    except:
        return {"status": "ignored"}

    t = text.lower()

    # Greetings
    if t in ["hi", "hello", "hey", "menu"]:
        send_message(sender, "Hello! Ask me anything about LPU.\n\nFor developer: type *developer*.")
        return {"status": "ok"}

    if "developer" in t or "who created" in t:
        send_message(sender, CREATOR_MESSAGE)
        return {"status": "ok"}

    # Time
    if t in ["time", "current time", "time now"]:
        now = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%I:%M %p")
        send_message(sender, f"Current time: {now}")
        return {"status": "ok"}

    # Weather
    if "weather" in t or "temperature" in t:
        city = t.replace("weather", "").replace("temperature", "").strip() or "Phagwara"
        send_message(sender, get_weather(city))
        return {"status": "ok"}

    # Rule-based LPU answer
    section = find_section(text)
    if section:
        send_message(sender, section)
        return {"status": "ok"}

    # AI fallback (educational only)
    if "lpu" in t or is_edu(text):
        send_message(sender, ai_fallback(text))
        return {"status": "ok"}

    # Block everything else
    send_message(sender, NON_LPU_REPLY)
    return {"status": "ok"}
