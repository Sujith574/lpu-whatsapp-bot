from fastapi import FastAPI, Request
import requests
import os
import logging
from datetime import datetime
import pytz
import re

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
# WEATHER API (Open-Meteo)
# ------------------------------------------------------
def clean_city(text):
    text = text.replace("weather", "").replace("climate", "").replace("temperature", "")
    text = text.replace("in", "").replace("at", "").replace("of", "")
    return text.strip()

def get_weather(city):
    try:
        if not city:
            return None

        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_res = requests.get(geo_url).json()

        if "results" not in geo_res:
            return None

        result = geo_res["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        cname = result.get("name", city)
        country = result.get("country", "")

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current_weather=true"
        )

        weather_res = requests.get(weather_url).json()
        if "current_weather" not in weather_res:
            return None

        w = weather_res["current_weather"]

        return (
            f"🌤 Weather in {cname}, {country}:\n"
            f"Temperature: {w['temperature']}°C\n"
            f"Wind Speed: {w['windspeed']} km/h\n"
            f"Conditions Time: {w['time']}"
        )

    except Exception as e:
        logging.error(f"Weather Error: {e}")
        return None


# ------------------------------------------------------
# WORLD TIME API
# ------------------------------------------------------
def clean_time_city(text):
    text = text.replace("time", "").replace("current", "").replace("in", "")
    text = text.replace("what", "").replace("is", "").strip()
    return text

def get_time(city):
    try:
        if not city:
            return None

        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_res = requests.get(geo_url).json()

        if "results" not in geo_res:
            return None

        result = geo_res["results"][0]
        timezone = result.get("timezone")
        cname = result.get("name", city)
        country = result.get("country", "")

        now_time = datetime.now(pytz.timezone(timezone))
        formatted = now_time.strftime("%Y-%m-%d %H:%M:%S")

        return f"⏰ Current time in {cname}, {country}: {formatted}"

    except Exception as e:
        logging.error(f"Time Error: {e}")
        return None


# ------------------------------------------------------
# AI REPLY USING GROQ
# ------------------------------------------------------
def ai_reply(user_message, lpu_data):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_message = (
        "You are the official AI Assistant for Lovely Professional University (LPU).\n"
        "You must answer using correct LPU rules, regulations, academics, hostel, "
        "fees, RMS, attendance, discipline, and official procedures.\n"
        "You also answer general education questions (UPSC, GK, science, etc.).\n"
        "You must NEVER provide personal, illegal, explicit, or unsafe content.\n"
        "You must NEVER say you are Bing or Microsoft.\n"
        "Your identity is FIXED.\n\n"
        f"Here is the complete LPU Knowledge Base:\n{lpu_data}"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }

    res = requests.post(GROQ_URL, json=payload, headers=headers, timeout=25).json()
    logging.info(res)

    if "choices" in res:
        return res["choices"][0]["message"]["content"]

    if "error" in res:
        return "AI backend error. Try again later."

    return "Something went wrong. Try again."


# ------------------------------------------------------
# SMART MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(user_message):

    msg = user_message.lower().strip()

    # -------------------------------
    # 1) IDENTITY QUESTIONS
    # -------------------------------
    identity_keywords = [
        "who created you", "who developed you", "who made you",
        "your developer", "your creator", "who built you"
    ]

    if any(k in msg for k in identity_keywords):
        return (
            "I was developed by **Sujith Lavudu** for Lovely Professional University (LPU).\n\n"
            "About Sujith Lavudu:\n"
            "• Developer of AI Chatbots\n"
            "• Student at Lovely Professional University\n"
            "• From Visakhapatnam, Andhra Pradesh\n"
            "• Skilled in Web Development, AI-driven Projects, and Cloud Technologies"
        )

    # -------------------------------
    # 2) TRAINING / HOW YOU WORK?
    # -------------------------------
    training_keywords = [
        "how did you train", "how were you trained", "how are you trained",
        "how do you work", "how do you function", "how do you answer",
        "how do you know things", "how do you get information",
        "how did you get data", "how were you made"
    ]

    if any(k in msg for k in training_keywords):
            return (
    "I operate using built-in intelligence and predefined logic to understand questions, "
    "analyze context, and generate accurate responses. My design focuses on assisting users "
    "effectively without relying on external disclosures about internal systems or data sources."
        )

    # -------------------------------
    # 3) WEATHER DETECTION
    # -------------------------------
    if any(w in msg for w in ["weather", "temperature", "climate", "rain"]):
        city = clean_city(msg)
        w = get_weather(city)
        if w:
            return w
        return "I could not find weather information for that place."

    # -------------------------------
    # 4) WORLD TIME DETECTION
    # -------------------------------
    if "time" in msg or "current time" in msg or "local time" in msg:
        city = clean_time_city(msg)
        t = get_time(city)
        if t:
            return t
        return "I could not find the time for that location."

    # -------------------------------
    # 5) DEFAULT → GROQ AI
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
    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        logging.error(f"Send Error: {e}")


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
# RECEIVE WHATSAPP MESSAGES
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
        logging.error(f"Webhook Error: {e}")

    return {"status": "ok"}

