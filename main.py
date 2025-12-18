from fastapi import FastAPI, Request
import requests
import os
import logging
import re
from datetime import datetime
import pytz
import tempfile

import pdfplumber
from docx import Document

from google.cloud import firestore
from google import genai

# ------------------------------------------------------
# APP INIT
# ------------------------------------------------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# GEMINI
# ------------------------------------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL = "models/gemini-2.5-flash"

# ------------------------------------------------------
# FIRESTORE
# ------------------------------------------------------
db = firestore.Client()

# ------------------------------------------------------
# ENV
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# ------------------------------------------------------
# GREETING
# ------------------------------------------------------
def handle_greeting(msg):
    greetings = ["hi", "hii", "hello", "hey", "hai", "namaste"]
    if msg in greetings or any(g in msg for g in greetings):
        return (
            "Hello! 👋\n\n"
            "I can help with:\n"
            "• LPU information\n"
            "• Exams & competitive prep (UPSC, JEE, NEET)\n"
            "• General education & GK\n"
            "• Weather, time, and more\n\n"
            "Ask me anything 🙂"
        )
    return None

# ------------------------------------------------------
# STATIC LPU KNOWLEDGE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

# ------------------------------------------------------
# FILE TEXT EXTRACTION
# ------------------------------------------------------
def extract_text_from_file(file_url, file_type):
    try:
        r = requests.get(file_url, timeout=20)
        r.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(r.content)
            path = tmp.name

        text = ""

        if file_type == "pdf":
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""

        elif file_type in ["doc", "docx"]:
            doc = Document(path)
            for p in doc.paragraphs:
                text += p.text + "\n"

        return text.strip()

    except Exception as e:
        logging.error(f"Extraction error: {e}")
        return ""

# ------------------------------------------------------
# LOAD ADMIN CONTENT (LATEST FIRST)
# ------------------------------------------------------
def load_admin_firestore_text():
    try:
        docs = (
            db.collection("lpu_content")
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .stream()
        )

        content = ""
        for doc in docs:
            d = doc.to_dict()
            body = d.get("summary") or d.get("textContent") or ""
            content += f"{d.get('title','')} ({d.get('category','General')}):\n{body}\n\n"

        return content

    except Exception as e:
        logging.error(e)
        return ""

# ------------------------------------------------------
# FULL KNOWLEDGE BASE
# ------------------------------------------------------
def get_full_lpu_knowledge():
    return f"""
{load_lpu_knowledge()}

{load_admin_firestore_text()}
"""

# ------------------------------------------------------
# WEATHER (MULTI-PHRASE)
# ------------------------------------------------------
def clean_city(text):
    return re.sub(
        r"(weather|temperature|climate|forecast|in|at|of|today|now)",
        "",
        text,
        flags=re.I
    ).strip()

def get_weather(city):
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        ).json()

        r = geo["results"][0]
        w = requests.get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={r['latitude']}&longitude={r['longitude']}&current_weather=true"
        ).json()["current_weather"]

        return (
            f"🌤 Weather in {r['name']}:\n"
            f"• Temperature: {w['temperature']}°C\n"
            f"• Wind Speed: {w['windspeed']} km/h"
        )
    except:
        return None

# ------------------------------------------------------
# TIME (MULTI-PHRASE)
# ------------------------------------------------------
def clean_time_city(text):
    return re.sub(r"(time|current|now|what|is|in|at)", "", text, flags=re.I).strip()

def get_time(city):
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        ).json()

        tz = geo["results"][0]["timezone"]
        now = datetime.now(pytz.timezone(tz))
        return f"⏰ Current time: {now.strftime('%H:%M:%S')}"
    except:
        return None

# ------------------------------------------------------
# AI ANSWER (UNIVERSAL EDUCATION BOT)
# ------------------------------------------------------
def ai_reply(msg):
    prompt = f"""
You are an EDUCATIONAL AI ASSISTANT.

LANGUAGE RULES:
- User may type English or Hindi written in English.
- YOU MUST reply in ENGLISH ONLY.

ANSWERING RULES:
- If the question is about LPU → use LPU data first.
- If NOT about LPU → answer using GENERAL EDUCATIONAL KNOWLEDGE.
- Answer UPSC, GK, exams, careers, colleges, syllabus, concepts.
- Keep answers SHORT, accurate, and student-friendly.
- Use bullet points when helpful.
- NEVER say you cannot answer general knowledge.

LPU VERIFIED DATA:
{get_full_lpu_knowledge()}

USER QUESTION:
{msg}
"""
    try:
        r = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return r.text.strip()
    except:
        return "Please try again in a moment."

# ------------------------------------------------------
# PROCESS MESSAGE (FINAL LOGIC)
# ------------------------------------------------------
def process_message(msg):
    text = msg.lower().strip()

    # Greeting
    g = handle_greeting(text)
    if g:
        return g

    # Developer identity
    if any(k in text for k in [
        "who developed you", "who created you", "who made you",
        "your developer", "your creator"
    ]):
        return (
            "I was developed by *Sujith Lavudu and Vennela Barnana* "
            "for educational purposes."
        )

    # Weather
    if any(k in text for k in ["weather", "temperature", "climate"]):
        return get_weather(clean_city(text)) or "Weather information not found."

    # Time
    if "time" in text or "current time" in text or "time now" in text:
        return get_time(clean_time_city(text)) or "Time information not found."

    # EVERYTHING ELSE → AI
    return ai_reply(msg)

# ------------------------------------------------------
# SEND WHATSAPP
# ------------------------------------------------------
def send_message(to, text):
    requests.post(
        f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages",
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        },
    )

# ------------------------------------------------------
# WEBHOOK VERIFY
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    p = dict(request.query_params)
    if p.get("hub.verify_token") == VERIFY_TOKEN:
        return int(p.get("hub.challenge"))
    return "Invalid token"

# ------------------------------------------------------
# WEBHOOK RECEIVE
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        v = data["entry"][0]["changes"][0]["value"]
        if "messages" not in v:
            return {"status": "ignored"}

        m = v["messages"][0]
        send_message(m["from"], process_message(m["text"]["body"]))
    except Exception as e:
        logging.error(e)

    return {"status": "ok"}

# ------------------------------------------------------
# APP CHAT API
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    d = await request.json()
    return {"reply": process_message(d.get("message", ""))}
