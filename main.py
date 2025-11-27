from fastapi import FastAPI, Request
import requests
import os
import logging
from datetime import datetime
import pytz

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# ENVIRONMENT VARIABLES
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ------------------------------------------------------
# LOAD LPU KNOWLEDGE BASE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "LPU knowledge could not be loaded."

LPU_KNOWLEDGE = load_lpu_knowledge()


# ------------------------------------------------------
# REAL-TIME WEATHER (Open-Meteo API)
# ------------------------------------------------------
def get_weather(city):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_res = requests.get(geo_url).json()

        if "results" not in geo_res:
            return None

        lat = geo_res["results"][0]["latitude"]
        lon = geo_res["results"][0]["longitude"]
        country = geo_res["results"][0].get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather_res = requests.get(weather_url).json()

        if "current_weather" not in weather_res:
            return None

        w = weather_res["current_weather"]

        return (
            f"🌤 Weather in {city.title()}, {country}:\n"
            f"Temperature: {w['temperature']}°C\n"
            f"Wind: {w['windspeed']} km/h\n"
            f"Time: {w['time']}"
        )
    except:
        return None


# ------------------------------------------------------
# REAL-TIME WORLD CLOCK
# ------------------------------------------------------
def get_time(city):
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_res = requests.get(geo_url).json()

        if "results" not in geo_res:
            return None

        timezone = geo_res["results"][0]["timezone"]

        now_time = datetime.now(pytz.timezone(timezone))
        formatted = now_time.strftime("%Y-%m-%d %H:%M:%S")

        country = geo_res["results"][0].get("country", "")

        return f"⏰ Current time in {city.title()}, {country}: {formatted}"
    except:
        return None


# ------------------------------------------------------
# AI CALL (Groq)
# ------------------------------------------------------
def ai_reply(user_message, lpu_data):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_message = (
        "You are LPU Assistant — an AI built ONLY for:\n"
        "• LPU rules, academics, fees, exams, RMS, hostel, discipline\n"
        "• Education, general knowledge, UPSC-level questions\n"
        "• Safe content ONLY (no personal, explicit, dating, hacking, etc.)\n"
        "You must ALWAYS use the LPU knowledge base if the question is related to LPU.\n"
        "Never say you are Bing, ChatGPT or Microsoft. Your identity is FIXED.\n\n"
        f"LPU Knowledge Base:\n{lpu_data}"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }

    res = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20).json()
    logging.info(res)

    if "choices" in res:
        return res["choices"][0]["message"]["content"]

    return "I'm facing some issues right now. Please try again."


# ------------------------------------------------------
# SMART MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(user_message):

    msg = user_message.lower().strip()

    # -------------------------------
    # IDENTITY → WHO CREATED YOU?
    # -------------------------------
    identity_keywords = [
        "who created you", "who developed you", "who made you",
        "your creator", "your developer", "who built you"
    ]

    if any(k in msg for k in identity_keywords):
        return (
            "I was created for Lovely Professional University (LPU) and developed by **Vennela Barnana**.\n\n"
            "About Vennela Barnana:\n"
            "• Author of *Unstoppable in 7 Days*\n"
            "• Developer of AI-based Chatbots\n"
            "• Studying at Lovely Professional University\n"
            "• From Srikakulam, Andhra Pradesh"
        )

    # -------------------------------
    # TRAINING → HOW DO YOU WORK?
    # -------------------------------
    training_keywords = [
        "how did you train", "how are you trained", "how were you trained",
        "how do you work", "how do you function", "how do you answer",
        "how do you know", "how did you get the data", "how do you get data",
        "how were you made", "how are you made"
    ]

    if any(k in msg for k in training_keywords):
        return (
            "I work using a combination of:\n"
            "• A detailed LPU Knowledge Base (hostel, exams, academics, fees, RMS, contacts)\n"
            "• Real-time APIs (weather + world time)\n"
            "• AI-powered reasoning for educational/general knowledge topics\n"
            "• Custom logic created by my developer, Vennela Barnana\n\n"
            "My data comes from the LPU knowledge base and APIs connected to me."
        )

    # -------------------------------
    # WEATHER
    # -------------------------------
    if "weather" in msg or "climate" in msg or "temperature" in msg:
        city = msg.replace("weather in", "").replace("weather", "").strip()
        w = get_weather(city)
        if w:
            return w
        return "I couldn't get weather for that place."

    # -------------------------------
    # WORLD TIME
    # -------------------------------
    if "time in" in msg or "current time" in msg or "what is the time" in msg:
        city = msg.replace("time in", "").replace("what is the time in", "").strip()
        t = get_time(city)
        if t:
            return t
        return "I couldn't fetch the time for that location."

    # -------------------------------
    # DEFAULT → GROQ AI
    # -------------------------------
    return ai_reply(user_message, LPU_KNOWLEDGE)


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
    requests.post(url, json=payload, headers=headers)


# ------------------------------------------------------
# WEBHOOK VERIFY
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"


# ------------------------------------------------------
# WEBHOOK RECEIVER
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        msg = messages[0]
        sender = msg["from"]
        text = msg.get("text", {}).get("body", "")

        reply = process_message(text)
        send_message(sender, reply)

    except Exception as e:
        logging.error(f"Webhook error: {e}")

    return {"status": "ok"}
