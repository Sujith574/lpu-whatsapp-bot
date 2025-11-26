from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz

app = FastAPI()
logging.basicConfig(level=logging.INFO)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENWEATHER_API_KEY = "c3802e9e6d0cabfd189dde96a6f58fae"

# *** UPDATED CREATOR MESSAGE ***
CREATOR_MESSAGE = (
    "I was developed for Lovely Professional University (LPU) and created by Vennela Barnana."
)

# -------------- WEATHER FUNCTIONS -------------------

def correct_city_name(city):
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
        url = f"https://api.openweatherMap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url).json()
        if r.get("cod") != 200:
            return "❌ City not found. Please try another city."

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
        return "⚠️ Unable to fetch weather currently."

# -------------- LOAD KNOWLEDGE BASE -------------------

def load_file(name):
    try:
        with open(name, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

LPU_KNOWLEDGE = load_file("lpu_knowledge.txt")
LPU_SECURITY = load_file("lpu_security.txt")
LPU_RESIDENTIAL = load_file("lpu_residential.txt")

FULL_KNOWLEDGE = (
    "\n\n===== LPU ACADEMIC & GENERAL RULES =====\n" + LPU_KNOWLEDGE +
    "\n\n===== LPU SECURITY RULES =====\n" + LPU_SECURITY +
    "\n\n===== LPU RESIDENTIAL HOSTEL HANDBOOK =====\n" + LPU_RESIDENTIAL
)

# -------------- RULE-BASED QUICK ANSWERS -------------------

def rule_based(text):
    t = text.lower()

    # Developer / creator detection
    if any(k in t for k in [
        "who built", "who created", "who made", "developer", "founder",
        "your creator", "your developer", "who built you", "who developed you"
    ]):
        return CREATOR_MESSAGE

    rules = {
        "attendance": "Minimum 75% attendance is mandatory. Below 75% = SOA.",
        "soa": "SOA means Shortage of Attendance (below 75%).",
        "hostel timing": "Girls: 10 PM • Boys: 11 PM",
        "hostel timings": "Girls: 10 PM • Boys: 11 PM",
        "gate pass": "Gate Pass is applied via UMS → Security & Safety → Online Sponsored Parent Pass / Hostel Leave.",
        "night out": "Night-out requires parent permission + warden approval.",
        "reappear": "Reappear fee is ₹500 per course. Only end-term marks change.",
        "cgpa": "CGPA = Σ(Credit × Grade Point) / ΣCredits.",
        "uniform": "Formal uniform mandatory Mon–Fri. Casual allowed Sat–Sun.",
        "dress": "Formal uniform mandatory Mon–Fri.",
        "fee": "Late fee ~₹100/day. Admit card blocked if fees pending.",
        "library": "Maintain silence. Late return of books may cause fines.",
        "medical": "Visit Uni-Health Center for medical attendance.",
        "grievance": "Submit grievance via UMS → RMS.",
        "parking": "Parking allowed only in designated parking areas.",
        "visitor": "Visitors allowed only with approved online gate pass.",
        "mess": "Mess timings: Breakfast 7:15–9:30, Lunch 11:30–3, Dinner 7:30–9:30."
    }

    for k in rules:
        if k in t:
            return rules[k]

    return None

# -------------- AI REPLY -------------------

def ai_reply(user_message):
    if not GROQ_API_KEY:
        return "AI backend is not configured."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are the official LPU Assistant. You must follow all LPU rules.\n"
        "If asked who built you, always reply exactly:\n"
        f"'{CREATOR_MESSAGE}'.\n"
        "Never say the university built you.\n"
        "Below is the entire LPU Knowledge Base. Use it to answer accurately:\n\n"
        f"{FULL_KNOWLEDGE}\n\n"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }

    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20)
        data = response.json()
        logging.info(data)

        if "choices" in data:
            reply = data["choices"][0]["message"]["content"]
        else:
            return "Unexpected AI response."

        # Safety fix for developer question
        if "lpu" in reply.lower() and "created" in reply.lower():
            return CREATOR_MESSAGE

        return reply

    except:
        return "AI is facing issues. Please try again later."

# -------------- SEND MESSAGE -------------------

def send_message(to, text):
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": text}
    }
    try:
        requests.post(url, json=payload, headers=headers)
    except:
        pass

# -------------- WEBHOOK VERIFY -------------------

@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"

# -------------- WEBHOOK HANDLER -------------------

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        entry = data["entry"][0]
        message = entry["changes"][0]["value"].get("messages", [])[0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")
    except:
        return {"status": "ignored"}

    # WELCOME MESSAGE
    if text.lower() in ["hi", "hello", "hey", "menu", "start"]:
        welcome = (
            "👋 Hello! I am your *LPU Assistant Bot*.\n\n"
            "You can ask me about:\n"
            "• Attendance & SOA rules\n"
            "• Hostel rules & timings\n"
            "• Residential handbook details\n"
            "• Gate pass & leave rules\n"
            "• Reappear/exam guidelines\n"
            "• Parking, RFID, security\n"
            "• CGPA, fees, placements\n\n"
            "How can I help you today? 😊"
        )
        send_message(sender, welcome)
        return {"status": "ok"}

    # TIME CHECK
    if text.lower() in ["time", "time now", "current time"]:
        india = pytz.timezone("Asia/Kolkata")
        now = datetime.datetime.now(india)
        send_message(sender, f"⏰ Current time: {now.strftime('%I:%M %p')}")
        return {"status": "ok"}

    # WEATHER
    t = text.lower()
    weather_keywords = ["weather", "temp", "temperature", "climate"]
    if any(k in t for k in weather_keywords):
        city = (
            t.replace("weather", "")
             .replace("temp", "")
             .replace("temperature", "")
             .replace("climate", "")
             .strip()
        )

        if city == "":
            send_message(sender, "🌦 Please type:\nweather delhi\nweather mumbai\nweather london")
            return {"status": "ok"}

        corrected = correct_city_name(city)
        if not corrected:
            send_message(sender, "⚠️ City not recognized.")
            return {"status": "ok"}

        send_message(sender, get_weather(corrected))
        return {"status": "ok"}

    # RULE BASED
    rb = rule_based(text)
    if rb:
        send_message(sender, rb)
        return {"status": "ok"}

    # AI REPLY
    reply = ai_reply(text)
    send_message(sender, reply)
    return {"status": "ok"}
