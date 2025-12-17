from fastapi import FastAPI, Request
import requests
import os
import logging
from datetime import datetime
import pytz
import re

from google.cloud import firestore

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# FIRESTORE INIT (Render uses service account automatically)
# ------------------------------------------------------
db = firestore.Client()

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
# LOAD STATIC LPU KNOWLEDGE (FILE)
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"File Load Error: {e}")
        return ""

# ------------------------------------------------------
# LOAD ADMIN TEXT FROM FIRESTORE
# ------------------------------------------------------
def load_admin_firestore_text():
    try:
        docs = db.collection("lpu_content") \
                 .where("type", "==", "text") \
                 .stream()

        content = ""
        for doc in docs:
            data = doc.to_dict()
            title = data.get("title", "")
            text = data.get("textContent", "")
            content += f"{title}:\n{text}\n\n"

        return content

    except Exception as e:
        logging.error(f"Firestore Read Error: {e}")
        return ""

# ------------------------------------------------------
# COMBINED KNOWLEDGE BASE
# ------------------------------------------------------
def get_full_lpu_knowledge():
    return f"""
===== OFFICIAL LPU RULES & REGULATIONS =====
{load_lpu_knowledge()}

===== LATEST ADMIN UPDATES =====
{load_admin_firestore_text()}
"""

# ------------------------------------------------------
# WEATHER API
# ------------------------------------------------------
def clean_city(text):
    text = re.sub(r"(weather|climate|temperature|in|at|of)", "", text, flags=re.I)
    return text.strip()

def get_weather(city):
    try:
        if not city:
            return None

        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        ).json()

        if "results" not in geo:
            return None

        r = geo["results"][0]
        lat, lon = r["latitude"], r["longitude"]

        weather = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        ).json()

        w = weather.get("current_weather")
        if not w:
            return None

        return (
            f"🌤 Weather in {r['name']}:\n"
            f"Temperature: {w['temperature']}°C\n"
            f"Wind Speed: {w['windspeed']} km/h\n"
            f"Time: {w['time']}"
        )

    except Exception as e:
        logging.error(e)
        return None

# ------------------------------------------------------
# WORLD TIME
# ------------------------------------------------------
def clean_time_city(text):
    text = re.sub(r"(time|current|what|is|in)", "", text, flags=re.I)
    return text.strip()

def get_time(city):
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        ).json()

        if "results" not in geo:
            return None

        r = geo["results"][0]
        now = datetime.now(pytz.timezone(r["timezone"]))
        return f"⏰ Current time in {r['name']}: {now.strftime('%Y-%m-%d %H:%M:%S')}"

    except Exception as e:
        logging.error(e)
        return None

# ------------------------------------------------------
# AI REPLY (GROQ)
# ------------------------------------------------------
def ai_reply(user_message):
    system_message = (
        "You are the official AI Assistant for Lovely Professional University (LPU).\n"
        "Answer ONLY using the verified information below.\n"
        "If information is missing, say:\n"
        "'I don't have updated information on this.'\n\n"
        f"{get_full_lpu_knowledge()}"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    res = requests.post(GROQ_URL, json=payload, headers=headers).json()

    if "choices" in res:
        return res["choices"][0]["message"]["content"]

    return "AI backend error."

# ------------------------------------------------------
# MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(user_message):
    msg = user_message.lower()

    if any(k in msg for k in ["who created you", "who made you"]):
        return "I was developed by Sujith Lavudu for Lovely Professional University."

    if any(k in msg for k in ["weather", "temperature", "climate"]):
        return get_weather(clean_city(msg)) or "Weather info not found."

    if "time" in msg:
        return get_time(clean_time_city(msg)) or "Time info not found."

    return ai_reply(user_message)

# ------------------------------------------------------
# WHATSAPP SEND
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
# VERIFY WEBHOOK
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid token"

# ------------------------------------------------------
# RECEIVE WHATSAPP
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = msg["from"]
        text = msg.get("text", {}).get("body", "")
        reply = process_message(text)
        send_message(sender, reply)
    except Exception as e:
        logging.error(e)

    return {"status": "ok"}

# ------------------------------------------------------
# CHAT API FOR MOBILE / WEB
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    message = data.get("message", "")
    if not message:
        return {"reply": "Please send a message."}
    return {"reply": process_message(message)}
