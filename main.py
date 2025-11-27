from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz
import re

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ---------------- ENVIRONMENT VARIABLES ----------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")

CREATOR_MESSAGE = "I was created for LPU students. Built by Vennela Barnana."
NON_LPU_REPLY = "I can answer only educational or LPU-related questions."

DATA_FILE = "data.txt"


# ---------------- LOAD DATA.TXT ----------------
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

        if section_pattern.match(stripped):  # New section heading
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
def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_KEY}&units=metric"
        r = requests.get(url).json()

        if r.get("cod") != 200:
            return "City not found."

        temp = r["main"]["temp"]
        feels = r["main"]["feels_like"]
        desc = r["weather"][0]["description"].title()

        return f"{city.title()} Weather:\nTemp: {temp}°C\nFeels: {feels}°C\n{desc}"

    except:
        return "Weather service unavailable."


# ---------------- RULE-BASED SEARCH ----------------
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


# ---------------- CHECK EDUCATIONAL QUERY ----------------
edu_words = [
    "attendance", "exam", "hostel", "leave", "cgpa", "ums", "rms",
    "semester", "mess", "warden", "wifi", "security", "placement",
    "library", "medical", "rfid", "rules"
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

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Give short, accurate LPU educational answers."},
            {"role": "user", "content": text}
        ]
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers
        ).json()

        return r["choices"][0]["message"]["content"]

    except Exception as e:
        logging.error(e)
        return "AI service unavailable."


# ---------------- SEND MESSAGE TO WHATSAPP ----------------
def send_message(to, body):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"  # FIXED VERSION
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": body}
    }

    try:
        requests.post(url, json=payload)
    except Exception as e:
        logging.error(e)


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
        send_message(sender, "Hello! Ask anything about LPU.\nType *developer* for creator info.")
        return {"status": "ok"}

    if "developer" in t:
        send_message(sender, CREATOR_MESSAGE)
        return {"status": "ok"}

    # Time
    if "time" in t:
        now = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%I:%M %p")
        send_message(sender, f"Current time: {now}")
        return {"status": "ok"}

    # Weather
    if "weather" in t or "temperature" in t:
        city = t.replace("weather", "").replace("temperature", "").strip() or "Phagwara"
        send_message(sender, get_weather(city))
        return {"status": "ok"}

    # Rule-based
    section = find_section(text)
    if section:
        send_message(sender, section)
        return {"status": "ok"}

    # AI fallback (education only)
    if "lpu" in t or is_edu(text):
        send_message(sender, ai_fallback(text))
        return {"status": "ok"}

    # Block all unrelated questions
    send_message(sender, NON_LPU_REPLY)
    return {"status": "ok"}
