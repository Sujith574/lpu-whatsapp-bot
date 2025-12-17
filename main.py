from fastapi import FastAPI, Request
import requests
import os
import logging
from datetime import datetime
import pytz
import re

from google.cloud import firestore
from google import genai

# ------------------------------------------------------
# APP INIT
# ------------------------------------------------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# GEMINI CLIENT (STABLE + SUPPORTED)
# ------------------------------------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
model = client.models.get("gemini-1.0-pro")

# ------------------------------------------------------
# FIRESTORE INIT (Render Secret File Auth)
# ------------------------------------------------------
db = firestore.Client()

# ------------------------------------------------------
# ENVIRONMENT VARIABLES
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# ------------------------------------------------------
# LOAD STATIC LPU KNOWLEDGE (GitHub file)
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"LPU knowledge file error: {e}")
        return ""

# ------------------------------------------------------
# LOAD ADMIN TEXT FROM FIRESTORE (FIXED SYNTAX)
# ------------------------------------------------------
def load_admin_firestore_text():
    try:
        docs = (
            db.collection("lpu_content")
            .where(filter=("type", "==", "text"))
            .stream()
        )

        content = ""
        for doc in docs:
            data = doc.to_dict()
            title = data.get("title", "")
            text = data.get("textContent", "")
            content += f"{title}:\n{text}\n\n"

        return content

    except Exception as e:
        logging.error(f"Firestore read error: {e}")
        return ""

# ------------------------------------------------------
# COMBINED KNOWLEDGE BASE
# ------------------------------------------------------
def get_full_lpu_knowledge():
    return f"""
===== OFFICIAL LPU RULES, POLICIES & STUDENT WINGS =====
{load_lpu_knowledge()}

===== LATEST OFFICIAL ADMIN UPDATES =====
{load_admin_firestore_text()}
"""

# ------------------------------------------------------
# WEATHER (EDUCATIONAL UTILITY)
# ------------------------------------------------------
def clean_city(text):
    return re.sub(r"(weather|climate|temperature|in|at|of)", "", text, flags=re.I).strip()

def get_weather(city):
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",
            timeout=10
        ).json()

        if "results" not in geo:
            return None

        r = geo["results"][0]
        lat, lon = r["latitude"], r["longitude"]

        weather = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true",
            timeout=10
        ).json()

        w = weather.get("current_weather")
        if not w:
            return None

        return (
            f"🌤 Weather in {r['name']}:\n"
            f"Temperature: {w['temperature']}°C\n"
            f"Wind Speed: {w['windspeed']} km/h"
        )
    except:
        return None

# ------------------------------------------------------
# WORLD TIME (EDUCATIONAL UTILITY)
# ------------------------------------------------------
def clean_time_city(text):
    return re.sub(r"(time|current|what|is|in)", "", text, flags=re.I).strip()

def get_time(city):
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",
            timeout=10
        ).json()

        if "results" not in geo:
            return None

        r = geo["results"][0]
        now = datetime.now(pytz.timezone(r["timezone"]))
        return f"⏰ Current time in {r['name']}: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    except:
        return None

# ------------------------------------------------------
# GEMINI AI RESPONSE (EDUCATION-ONLY, STABLE)
# ------------------------------------------------------
def ai_reply(user_message):
    prompt = f"""
You are the Official Educational AI Assistant for Lovely Professional University (LPU).

RULES:
- Answer ONLY education and LPU-related queries
- Use ONLY the verified information below
- If not educational, reply exactly:
  "I am designed only for educational and LPU-related queries."
- If info missing, reply exactly:
  "I don't have updated information on this."

VERIFIED INFORMATION:
{get_full_lpu_knowledge()}

QUESTION:
{user_message}
"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return "AI service is temporarily unavailable."

# ------------------------------------------------------
# MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(user_message):
    msg = user_message.lower()

    if any(k in msg for k in ["who created you", "who developed you", "who made you"]):
        return "I was developed by Sujith Lavudu for Lovely Professional University (LPU)."

    if any(k in msg for k in ["weather", "temperature", "climate"]):
        return get_weather(clean_city(msg)) or "Weather information not found."

    if "time" in msg:
        return get_time(clean_time_city(msg)) or "Time information not found."

    return ai_reply(user_message)

# ------------------------------------------------------
# SEND WHATSAPP MESSAGE
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
    requests.post(url, json=payload, headers=headers, timeout=10)

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
# RECEIVE WHATSAPP (SAFE HANDLING)
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    try:
        entry = data.get("entry", [])
        if not entry:
            return {"status": "ignored"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ignored"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return {"status": "ignored"}

        msg = messages[0]
        sender = msg.get("from")
        text = msg.get("text", {}).get("body", "")

        if sender and text:
            reply = process_message(text)
            send_message(sender, reply)

    except Exception as e:
        logging.error(e)

    return {"status": "ok"}

# ------------------------------------------------------
# CHAT API (APP / WEB)
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    message = data.get("message", "")
    if not message:
        return {"reply": "Please send a message."}
    return {"reply": process_message(message)}
