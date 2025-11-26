from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ENV
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "c3802e9e6d0cabfd189dde96a6f58fae")

# Creator Message
CREATOR_MESSAGE = "I was developed for Lovely Professional University (LPU) and created by Vennela Barnana."

# ---------------- WEATHER HELPERS ----------------
def correct_city_name(city):
    if "lpu" in city or "phagwara" in city:
        return "Phagwara"
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_API_KEY}"
        r = requests.get(url).json()
        if not r:
            return None
        return r[0]["name"]
    except:
        return None


def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url).json()

        if r.get("cod") != 200:
            return "❌ City not found. Try again."

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
        return "⚠️ Unable to fetch weather."


# ---------------- LOAD ALL TEXT FILES ----------------
def load_sections():
    folder = "sections"
    data = {}

    if not os.path.exists(folder):
        return data

    for f in os.listdir(folder):
        if f.endswith(".txt"):
            try:
                with open(os.path.join(folder, f), "r", encoding="utf-8") as file:
                    key = f.replace(".txt", "")
                    data[key] = file.read().strip()
            except:
                continue
    return data


SECTIONS = load_sections()


# ---------------- RULE-BASED LPU DETECTION ----------------
def find_lpu_answer(text):
    t = text.lower()

    # Direct creator check
    creator_words = ["who created", "who built", "who made", "developer", "founder"]
    if any(x in t for x in creator_words):
        return CREATOR_MESSAGE

    # Special high-priority detection
    if any(x in t for x in ["60", "low attendance", "below 75", "my attendance"]):
        return SECTIONS.get("attendance", "")

    if "leave" in t and any(x in t for x in ["denied", "problem", "issue"]):
        return SECTIONS.get("hostel_leave_rules", "")

    if "visitor" in t or "parent pass" in t:
        return SECTIONS.get("visitor_rules", "")

    if "rfid" in t or "id card" in t or "lost card" in t:
        return SECTIONS.get("id_card", "")

    if "mess" in t or "food" in t:
        return SECTIONS.get("mess_rules", "")

    # Match based on filename keywords
    for key, content in SECTIONS.items():
        if key.replace("_", " ") in t:
            return content

    # Fuzzy keyword match
    keywords = {
        "attendance": "attendance",
        "leave": "hostel_leave_rules",
        "visitor": "visitor_rules",
        "parking": "parking",
        "rfid": "rfid_and_parking_rules",
        "mess": "mess_rules",
        "hostel": "hostel_rules",
        "timing": "hostel_timings",
        "library": "library",
        "discipline": "discipline",
        "exam": "exam_rules",
        "reappear": "exam_reappear",
        "medical": "medical",
        "transport": "transport",
        "wifi": "wifi_network",
        "security": "security",
        "safety": "security_and_safety",
        "rms": "rm_system"
    }

    for word, section in keywords.items():
        if word in t and section in SECTIONS:
            return SECTIONS[section]

    return None  # means "not an LPU question"


# ---------------- AI FALLBACK ----------------
def ai_fallback(text):
    if not GROQ_API_KEY:
        return "AI backend offline."

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Answer briefly. If the question is about LPU, reply: 'Please ask LPU-related questions only.'"},
            {"role": "user", "content": text}
        ],
        "temperature": 0.2
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers).json()
        return r["choices"][0]["message"]["content"]
    except:
        return "AI is unavailable."


# ---------------- SEND MESSAGE ----------------
def send_message(to, body):
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": body}}

    try:
        requests.post(url, json=payload)
    except:
        pass


# ---------------- WEBHOOK VERIFY ----------------
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

    lower = text.lower()

    # Greeting
    if lower in ["hi", "hello", "hey", "start", "menu"]:
        send_message(sender,
            "👋 Hello! I am your *Official LPU Assistant Bot*.\n\n"
            "Ask me anything about:\n"
            "• Attendance & SOA\n"
            "• Hostel rules\n"
            "• Leave rules\n"
            "• RFID / Visitor Pass\n"
            "• Mess, Hostel, Security\n"
            "• CGPA, Exams, Reappear\n\n"
            "How can I help you?"
        )
        return {"status": "ok"}

    # Time
    if lower in ["time", "current time", "time now"]:
        now = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%I:%M %p")
        send_message(sender, f"⏰ Current time: {now}")
        return {"status": "ok"}

    # Weather
    if "weather" in lower or "temperature" in lower or "climate" in lower:
        city = lower.replace("weather", "").replace("temperature", "").replace("climate", "").strip()
        if city == "" or "lpu" in city:
            city = "Phagwara"
        corrected = correct_city_name(city)
        if not corrected:
            send_message(sender, "City not recognized.")
        else:
            send_message(sender, get_weather(corrected))
        return {"status": "ok"}

    # Rule-based LPU reply
    rule_ans = find_lpu_answer(lower)
    if rule_ans:
        send_message(sender, rule_ans)
        return {"status": "ok"}

    # AI fallback (non-LPU questions)
    send_message(sender, ai_fallback(text))
    return {"status": "ok"}
