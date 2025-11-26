from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz
import glob

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ---------------- ENVIRONMENT VARIABLES ----------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "c3802e9e6d0cabfd189dde96a6f58fae")

# ---------------- CREATOR RULE ----------------
CREATOR_MESSAGE = (
    "I was developed for Lovely Professional University (LPU) and created by Vennela Barnana."
)

# ---------------- LOAD ALL TXT FILES ----------------
def load_all_sections():
    data = ""
    for file in sorted(glob.glob("sections/*.txt")):
        try:
            with open(file, "r", encoding="utf-8") as f:
                name = file.replace("sections/", "")
                data += f"\n\n===== {name.upper()} =====\n"
                data += f.read()
        except:
            pass
    return data

FULL_KB = load_all_sections()

# ---------------- WEATHER HELPERS ----------------
def correct_city(city):
    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_API_KEY}"
        r = requests.get(url, timeout=8).json()
        if not r:
            return None
        return r[0]["name"]
    except:
        return None

def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=8).json()
        if r.get("cod") != 200:
            return "❌ City not found. Please try again."
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

# ---------------- QUICK RULE-BASED ANSWERS ----------------
def quick_reply(text):
    t = text.lower()

    # Creator rule
    if any(key in t for key in ["who created", "who built", "developer", "founder", "who made you"]):
        return CREATOR_MESSAGE

    # Time
    if t in ["time", "time now", "current time", "what is the time"]:
        india = pytz.timezone("Asia/Kolkata")
        now = datetime.datetime.now(india).strftime("%I:%M %p")
        return f"⏰ Current time: {now}"

    # Weather at LPU
    if "weather" in t and ("lpu" in t or "phagwara" in t or "punjab" in t):
        return get_weather("Phagwara")

    # Basic rules
    rules = {
        "attendance": "Minimum 75% attendance is mandatory. Below 75% = SOA.",
        "soa": "SOA = Shortage of Attendance (below 75%).",
        "cgpa": "CGPA = Σ(Credit × Grade Point) / ΣCredits.",
        "reappear": "Reappear fee = ₹500 per course. Only end-term marks change.",
        "hostel timing": "Girls: 10 PM • Boys: 11 PM.",
        "mess": "Mess timings: Breakfast 7:15–9:30 • Lunch 11:30–3:00 • Dinner 7:30–9:30",
        "night out": "Night-out requires parent approval + warden approval.",
        "gate pass": "Gate pass via UMS → Security & Safety → Online Sponsored Parent Pass.",
        "library": "Maintain silence. Late return fines apply.",
        "medical": "Visit Uni-Health Center for medical treatment.",
        "parking": "Park only in designated areas. Speed limit: 30 km/hr.",
    }
    for k, v in rules.items():
        if k in t:
            return v

    return None  # allow fallback to AI

# ---------------- AI HANDLER ----------------
def ai_answer(msg):
    if not GROQ_API_KEY:
        return "AI backend not configured."

    system_prompt = (
        "You are the official LPU Assistant bot.\n"
        "Use the provided LPU rules & knowledge to answer accurately.\n"
        f"If asked who created you, ALWAYS reply: '{CREATOR_MESSAGE}'.\n"
        "Never say LPU created you.\n\n"
        "All LPU rules, regulations, and policies are below:\n"
        f"{FULL_KB}\n"
    )

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": msg}
        ],
        "temperature": 0.2,
        "max_tokens": 250
    }

    try:
        r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20).json()
        if "choices" not in r:
            return "AI error. Try again."

        reply = r["choices"][0]["message"]["content"]

        # Enforce creator rule
        if ("created" in reply.lower() or "developed" in reply.lower()) and "lpu" in reply.lower():
            return CREATOR_MESSAGE

        return reply

    except Exception as e:
        logging.error(e)
        return "AI is facing issues. Try again later."

# ---------------- SEND MESSAGE ----------------
def send_message(to, text):
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}

    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        logging.error(e)

# ---------------- WEBHOOK VERIFY ----------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"

# ---------------- WEBHOOK HANDLER ----------------
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

    # Welcome message
    if text.lower() in ["hi", "hello", "hey", "start", "menu"]:
        send_message(
            sender,
            "👋 Hello! I am your *Official LPU Assistant Bot*.\n\n"
            "Ask anything about:\n"
            "• Attendance & SOA\n"
            "• Hostel & residential rules\n"
            "• Leave & gate pass\n"
            "• CGPA, exams, reappear\n"
            "• Security, parking, RFID\n"
            "• Mess, timings, medical\n\n"
            "How can I help you today? 😊"
        )
        return {"status": "ok"}

    # Quick rule-based reply
    qr = quick_reply(text)
    if qr:
        send_message(sender, qr)
        return {"status": "ok"}

    # Weather (generic)
    if "weather" in text.lower():
        city = (
            text.lower()
            .replace("weather", "")
            .replace("in", "")
            .replace("at", "")
            .strip()
        )
        if city == "":
            send_message(sender, "🌦 Example: weather delhi / weather mumbai / weather lpu")
            return {"status": "ok"}

        corrected = correct_city(city)
        if not corrected:
            send_message(sender, "⚠️ City not recognized. Try another city.")
            return {"status": "ok"}

        send_message(sender, get_weather(corrected))
        return {"status": "ok"}

    # AI fallback
    reply = ai_answer(text)
    send_message(sender, reply)
    return {"status": "ok"}
