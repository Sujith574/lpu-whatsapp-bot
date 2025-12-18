from fastapi import FastAPI, Request
import requests
import os
import logging
import re
from datetime import datetime
import pytz

from google.cloud import firestore
from google import genai

# ------------------------------------------------------
# APP INIT
# ------------------------------------------------------
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# GEMINI CONFIG
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
# GREETINGS
# ------------------------------------------------------
def handle_greeting(msg: str):
    greetings = ["hi", "hii", "hello", "hey", "hai", "namaste"]
    if msg in greetings or any(g in msg for g in greetings):
        return (
            "Hello! 👋\n\n"
            "I can help you with:\n"
            "• LPU exams, hostels, fees, attendance\n"
            "• Education, GK, UPSC\n"
            "• Weather, date, and time\n\n"
            "Please ask your question."
        )
    return None

# ------------------------------------------------------
# LOAD ADMIN LPU CONTENT (LATEST FIRST)
# ------------------------------------------------------
def load_admin_lpu_content():
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
            content += f"{d.get('title','')}:\n{body}\n\n"

        return content.strip()
    except Exception as e:
        logging.error(e)
        return ""

# ------------------------------------------------------
# CHECK IF QUESTION IS ABOUT LPU
# ------------------------------------------------------
def is_lpu_question(msg: str) -> bool:
    keywords = [
        "lpu", "lovely professional university", "ums", "attendance",
        "exam", "hostel", "fee", "fees", "placement", "semester",
        "registration", "reappear", "mid term", "end term"
    ]
    msg = msg.lower()
    return any(k in msg for k in keywords)

# ------------------------------------------------------
# GEMINI RESPONSE
# ------------------------------------------------------
def gemini_reply(user_message: str, lpu_context: str = "") -> str:
    prompt = f"""
You are the Official AI Assistant.

RULES (STRICT):
- Reply ONLY in ENGLISH.
- Be short, accurate, and professional.
- If LPU data is provided, prioritize it.
- Never say you lack real-time access.
- Answer confidently.

LPU DATA (if any):
{lpu_context}

USER QUESTION:
{user_message}
"""
    try:
        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return res.text.strip()
    except Exception as e:
        logging.error(e)
        return "The service is temporarily busy. Please try again."

# ------------------------------------------------------
# MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # Greeting
    greeting = handle_greeting(text)
    if greeting:
        return greeting

    # --------------------------------------------------
    # OFFICIAL IDENTITIES (HIGHEST PRIORITY)
    # --------------------------------------------------
    if any(k in text for k in [
        "who developed you", "who created you", "who made you",
        "your developer", "your creator", "founder of this bot"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, software developer, and author.\n\n"
            "He is the co-creator of the LPU Vertosewa AI Assistant and "
            "co-author of the book “Decode the Code”."
        )

    if "vennela barnana" in text or "vennela" in text:
        return (
            "Vennela Barnana is an author, researcher, and co-creator of the "
            "LPU Vertosewa AI Assistant.\n\n"
            "She is the co-author of the book “Decode the Code” and works on "
            "AI-driven educational initiatives."
        )

    # --------------------------------------------------
    # LPU QUESTIONS → FIRESTORE FIRST
    # --------------------------------------------------
    if is_lpu_question(msg):
        lpu_data = load_admin_lpu_content()
        if lpu_data:
            return gemini_reply(msg, lpu_data)
        else:
            return gemini_reply(msg)

    # --------------------------------------------------
    # EVERYTHING ELSE → GEMINI ONLY
    # (Weather, Time, GK, UPSC, Education, People)
    # --------------------------------------------------
    return gemini_reply(msg)

# ------------------------------------------------------
# SEND WHATSAPP MESSAGE
# ------------------------------------------------------
def send_message(to: str, text: str):
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
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid token"

# ------------------------------------------------------
# WEBHOOK RECEIVE (WHATSAPP)
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return {"status": "ignored"}

        msg = value["messages"][0]
        reply = process_message(msg["text"]["body"])
        send_message(msg["from"], reply)

    except Exception as e:
        logging.error(e)

    return {"status": "ok"}

# ------------------------------------------------------
# APP CHAT API (FLUTTER)
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    return {"reply": process_message(data.get("message", ""))}
