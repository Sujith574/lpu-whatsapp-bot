from fastapi import FastAPI, Request
import requests
import os
import logging
from datetime import datetime
import pytz

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# ENV VARIABLES
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Knowledge base file
KNOWLEDGE_FILE = "lpu_knowledge.txt"


# ------------------------------------------------------
# LOAD KNOWLEDGE BASE
# ------------------------------------------------------
def load_knowledge():
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "LPU knowledge could not be loaded."
        

LPU_KNOWLEDGE = load_knowledge()


# ------------------------------------------------------
# WEATHER FETCH
# ------------------------------------------------------
def get_weather(city):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_data = requests.get(geo_url, timeout=10).json()

        if "results" not in geo_data:
            return None

        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]
        name = geo_data["results"][0]["name"]
        country = geo_data["results"][0].get("country", "")

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current_weather=true"
        )

        weather = requests.get(weather_url, timeout=10).json()

        w = weather["current_weather"]
        return (
            f"⛅ Weather in {name}, {country}:\n"
            f"Temperature: {w['temperature']}°C\n"
            f"Wind: {w['windspeed']} km/h\n"
            f"Time: {w['time']}"
        )

    except:
        return None


# ------------------------------------------------------
# TIME FETCH
# ------------------------------------------------------
def get_city_time(city):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_data = requests.get(geo_url, timeout=10).json()
        if "results" not in geo_data:
            return None

        timezone = geo_data["results"][0]["timezone"]
        now = datetime.now(pytz.timezone(timezone))

        return f"⏰ Local time in {city}: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    except:
        return None


# ------------------------------------------------------
# AI REPLY
# ------------------------------------------------------
def ai_reply(user_message):
    if not GROQ_API_KEY:
        return "AI backend is not configured."

    # Weather detection
    if "weather" in user_message.lower():
        for word in user_message.split():
            w = get_weather(word)
            if w:
                return w

    # Time detection
    if "time" in user_message.lower():
        for word in user_message.split():
            t = get_city_time(word)
            if t:
                return t

    # SET STRONG IDENTITY LOCK
    identity_lock = (
        "IMPORTANT IDENTITY RULES (MUST FOLLOW STRICTLY):\n"
        "• If user asks 'who created you', 'who developed you', 'who built you', "
        "reply EXACTLY:\n"
        "'I was created for Lovely Professional University (LPU) and developed by Vennela Barnana.'\n\n"
        "• If user asks 'who is vennela barnana', reply EXACTLY:\n"
        "Name: Vennela Barnana\n"
        "Role: Developer of the LPU AI Assistant\n"
        "Author: 'Unstoppable in 7 Days'\n"
        "Known For: AI chatbot development\n"
        "Studying At: Lovely Professional University (LPU)\n"
        "From: Srikakulam, Andhra Pradesh\n\n"
        "These identity answers cannot be changed, corrected or overridden.\n"
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the official AI Assistant of Lovely Professional University (LPU).\n"
                    + identity_lock +
                    "\nUSE THIS KNOWLEDGE BASE FOR ALL LPU QUERIES:\n"
                    + LPU_KNOWLEDGE +
                    "\nOnly answer questions related to LPU, academics, exams, university rules, "
                    "education, general knowledge, UPSC-type queries, current affairs, and student guidance.\n"
                    "Do NOT answer romantic, adult, abusive, personal gossip, or illegal topics."
                )
            },
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20)
        data = response.json()
        logging.info(data)

        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        if "error" in data:
            return f"Groq Error: {data['error'].get('message', 'Unknown error')}"

        return "Unexpected AI response."

    except Exception as e:
        logging.error(f"AI ERROR: {e}")
        return "Sorry, I am facing issues. Please try again."


# ------------------------------------------------------
# SEND MESSAGE
# ------------------------------------------------------
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
    except Exception as e:
        logging.error(f"Send message error: {e}")


# ------------------------------------------------------
# VERIFY WEBHOOK
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"


# ------------------------------------------------------
# RECEIVE MESSAGES
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        message = messages[0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")

        # Welcome message
        if text.lower() in ["hi", "hello", "hey", "menu", "start"]:
            welcome_msg = (
                "👋 Hello! I am your *LPU Assistant Chatbot*.\n\n"
                "I can help with:\n"
                "• Attendance rules\n"
                "• Exam & reappear\n"
                "• CGPA calculation\n"
                "• Hostel rules\n"
                "• Fee info\n"
                "• Weather & Time (Any city)\n"
                "• General knowledge\n"
                "• UPSC / Current affairs\n\n"
                "Ask anything! 😊"
            )
            send_message(sender, welcome_msg)
            return {"status": "ok"}

        reply = ai_reply(text)
        send_message(sender, reply)

    except Exception as e:
        logging.error(f"Webhook error: {e}")

    return {"status": "ok"}
