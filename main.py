from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz
from fuzzywuzzy import process

app = FastAPI()
logging.basicConfig(level=logging.INFO)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENWEATHER_API_KEY = "c3802e9e6d0cabfd189dde96a6f58fae"

CREATOR_MESSAGE = (
    "I was created and developed by the Founders of Dream Sphere, "
    "and I serve as the official AI Assistant for Lovely Professional University (LPU)."
)

CITIES = [
    "delhi", "mumbai", "hyderabad", "chennai", "kolkata", "bangalore",
    "pune", "ahmedabad", "jaipur", "lucknow", "visakhapatnam", "vijayawada",
    "kochi", "nagpur", "surat", "patna", "bhopal", "chandigarh", "indore",
    "gurgaon", "noida", "trivandrum", "madurai", "coimbatore", "goa",
    "mysore", "rajkot", "varanasi", "kanpur"
]

def correct_city_name(city):
    best_match = process.extractOne(city, CITIES)
    if best_match and best_match[1] > 60:
        return best_match[0]
    return None

def get_weather(city):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
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

def load_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Knowledge base not found."

LPU_DATA = load_knowledge()

def rule_based(text):
    t = text.lower()
    if (
        "who built you" in t or
        "who created you" in t or
        "who made you" in t or
        "who developed you" in t or
        "developer" in t or
        "founder" in t or
        "your creator" in t or
        "your developer" in t or
        "who are your founders" in t
    ):
        return CREATOR_MESSAGE
    rules = {
        "attendance": "Minimum 75% attendance required. Below that is SOA (Shortage of Attendance).",
        "soa": "SOA = Shortage of Attendance (below 75%).",
        "hostel": "Hostel timings → Girls: 10 PM, Boys: 11 PM.",
        "timing": "Hostel timings → Girls: 10 PM, Boys: 11 PM.",
        "gate pass": "Gate Pass must be applied through UMS to exit campus.",
        "night out": "Night-out requires parent approval + warden permission.",
        "reappear": "Reappear fee is ₹500 per course. Only end-term marks are replaced.",
        "cgpa": "CGPA = Σ(Credit × Grade Point) / ΣCredits.",
        "uniform": "Formal uniform mandatory Mon–Fri. Casual allowed Sat–Sun.",
        "dress": "Formal uniform mandatory Mon–Fri. Casual allowed Sat–Sun.",
        "fee": "Late fee approx ₹100/day. No admit card if fees pending.",
        "library": "Silence mandatory. Late return of books is not allowed.",
        "medical": "Visit University Hospital for medical attendance.",
        "grievance": "Submit grievance via UMS → RMS (Relationship Management System).",
    }
    for key in rules:
        if key in t:
            return rules[key]
    return None

def ai_reply(user_message):
    if not GROQ_API_KEY:
        return "AI backend is not configured."
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    system_prompt = (
        "You are the official AI Assistant for Lovely Professional University (LPU).\n"
        "Use the LPU Knowledge Base to answer accurately.\n\n"
        "IMPORTANT RULE:\n"
        f"If anyone asks who built you or developed you, always answer: '{CREATOR_MESSAGE}'.\n"
        "Never say LPU created you.\n\n"
        f"LPU KNOWLEDGE BASE:\n{LPU_DATA}\n\n"
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
        elif "error" in data:
            return f"Groq Error: {data['error'].get('message', 'Unknown error')}"
        else:
            return "Unexpected AI response."
        rl = reply.lower()
        if (
            ("created" in rl or "developed" in rl or "built" in rl or "founder" in rl)
            and ("lpu" in rl or "university" in rl or "official" in rl)
        ):
            reply = CREATOR_MESSAGE
        return reply
    except Exception as e:
        logging.error(f"AI ERROR: {e}")
        return "AI is facing issues. Please try again later."

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

@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"

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

    if text.lower() in ["hi", "hello", "hey", "menu", "start"]:
        welcome = (
            "👋 Hello! I am your *LPU Assistant Bot*.\n\n"
            "Ask me anything about:\n"
            "• Attendance rules\n"
            "• Hostel timings\n"
            "• Reappear & exam rules\n"
            "• CGPA calculation\n"
            "• Fees & fines\n"
            "• Dress code\n"
            "• LPU regulations\n"
            "• Academic processes\n\n"
            "How can I help you today? 😊"
        )
        send_message(sender, welcome)
        return {"status": "ok"}

    if text.lower() in ["time", "time now", "current time", "what is the time"]:
        india = pytz.timezone("Asia/Kolkata")
        now = datetime.datetime.now(india)
        current_time = now.strftime("%I:%M %p")
        send_message(sender, f"⏰ Current time: {current_time}")
        return {"status": "ok"}

    t = text.lower()
    weather_keywords = [
        "weather", "wether", "waether", "wheather",
        "climate", "temp", "temprature", "temperature"
    ]

    if any(k in t for k in weather_keywords):
        clean = (
            t.replace("weather", "")
             .replace("wether", "")
             .replace("waether", "")
             .replace("wheather", "")
             .replace("climate", "")
             .replace("temp", "")
             .replace("temperature", "")
             .replace("temprature", "")
             .replace("in", "")
             .replace("at", "")
             .replace("of", "")
             .strip()
        )

        if clean == "":
            send_message(sender, "🌍 Please type like:\nweather hyderabad\nweather mumbai\nweather delhi")
            return {"status": "ok"}

        corrected = correct_city_name(clean)
        if not corrected:
            send_message(sender, "⚠️ City not recognized. Try full city name.")
            return {"status": "ok"}

        weather_report = get_weather(corrected)
        send_message(sender, weather_report)
        return {"status": "ok"}

    rb = rule_based(text)
    if rb:
        send_message(sender, rb)
        return {"status": "ok"}

    reply = ai_reply(text)
    send_message(sender, reply)
    return {"status": "ok"}
