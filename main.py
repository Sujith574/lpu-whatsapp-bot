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
# GEMINI CLIENT (CONFIRMED WORKING)
# ------------------------------------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL = "models/gemini-2.5-flash"

# ------------------------------------------------------
# FIRESTORE INIT
# ------------------------------------------------------
db = firestore.Client()

# ------------------------------------------------------
# ENV VARIABLES
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# ------------------------------------------------------
# GREETING HANDLER
# ------------------------------------------------------
def handle_greeting(msg: str):
    greetings = ["hi", "hii", "hello", "hey", "namaste", "hai"]

    if msg in greetings:
        return (
            "Namaste! 🙏\n\n"
            "How can I assist you today?\n"
            "You can ask questions related to *Lovely Professional University (LPU)* "
            "or general education."
        )

    if any(g in msg for g in greetings):
        return (
            "Hello! 👋\n\n"
            "How can I help you today?\n"
            "Feel free to ask about *LPU academics, hostels, fees, exams,* "
            "or any general education topic."
        )

    return None

# ------------------------------------------------------
# LOAD STATIC LPU KNOWLEDGE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"LPU knowledge file error: {e}")
        return ""

# ------------------------------------------------------
# LOAD ADMIN DATA FROM FIRESTORE
# ------------------------------------------------------
def load_admin_firestore_text():
    try:
        docs = db.collection("lpu_content").where("type", "==", "text").stream()
        content = ""
        for doc in docs:
            d = doc.to_dict()
            content += f"{d.get('title','')}:\n{d.get('textContent','')}\n\n"
        return content
    except Exception as e:
        logging.error(f"Firestore read error: {e}")
        return ""

# ------------------------------------------------------
# COMBINED KNOWLEDGE
# ------------------------------------------------------
def get_full_lpu_knowledge():
    return f"""
{load_lpu_knowledge()}

{load_admin_firestore_text()}
"""

# ------------------------------------------------------
# SIMPLE KNOWLEDGE CHECK
# ------------------------------------------------------
def knowledge_exists(question: str):
    kb = get_full_lpu_knowledge().lower()
    words = [w for w in question.lower().split() if len(w) > 3]
    return any(w in kb for w in words)

# ------------------------------------------------------
# WEATHER
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
        weather = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={r['latitude']}&longitude={r['longitude']}&current_weather=true",
            timeout=10
        ).json()

        w = weather.get("current_weather")
        if not w:
            return None

        return (
            f"🌤 *Weather in {r['name']}*\n"
            f"• Temperature: {w['temperature']}°C\n"
            f"• Wind Speed: {w['windspeed']} km/h"
        )
    except:
        return None

# ------------------------------------------------------
# TIME
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
        return f"⏰ *Current time in {r['name']}*: {now.strftime('%H:%M:%S')}"
    except:
        return None

# ------------------------------------------------------
# GEMINI AI RESPONSE
# ------------------------------------------------------
def ai_reply(user_message):
    prompt = f"""
You are the Official AI Assistant for Lovely Professional University (LPU).

INSTRUCTIONS:
- First, try to answer using VERIFIED LPU INFORMATION.
- If not found, answer using general educational knowledge.
- Understand short, informal, or mixed-language questions naturally.
- Keep answers SHORT, clear, and professional.
- Prefer bullet points.
- Do NOT mention sources.

VERIFIED LPU INFORMATION:
{get_full_lpu_knowledge()}

QUESTION:
{user_message}
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return "AI service is temporarily unavailable."

# ------------------------------------------------------
# MESSAGE PROCESSOR (FINAL FLOW)
# ------------------------------------------------------
def process_message(user_message):
    msg = user_message.lower().strip()

    # 1️⃣ Greeting
    greeting = handle_greeting(msg)
    if greeting:
        return greeting

    # 2️⃣ Utilities
    if any(k in msg for k in ["weather", "temperature", "climate"]):
        return get_weather(clean_city(msg)) or "Weather information not found."

    if "time" in msg:
        return get_time(clean_time_city(msg)) or "Time information not found."

    # 3️⃣ LPU knowledge → Gemini formatting
    if knowledge_exists(user_message):
        return ai_reply(user_message)

    # 4️⃣ Fallback → Gemini
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
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text
        }
    }

    r = requests.post(url, headers=headers, json=payload)
    logging.info(f"WhatsApp send: {r.status_code} | {r.text}")

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
        entry = data.get("entry", [])
        if not entry:
            return {"status": "ignored"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ignored"}

        value = changes[0].get("value", {})
        if "messages" not in value:
            return {"status": "ignored"}

        msg = value["messages"][0]
        sender = msg.get("from")
        text = msg.get("text", {}).get("body", "")

        if sender and text:
            reply = process_message(text)
            send_message(sender, reply)

    except Exception as e:
        logging.error(f"Webhook error: {e}")

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
