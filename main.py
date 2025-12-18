from fastapi import FastAPI, Request
import requests
import os
import logging
import re
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
def handle_greeting(msg):
    greetings = ["hi", "hii", "hello", "hey", "hai", "namaste"]
    if msg in greetings or any(g in msg for g in greetings):
        return (
            "Hello! 👋\n\n"
            "I am the Official AI Assistant for Lovely Professional University (LPU).\n"
            "You may ask about:\n"
            "• LPU academics & rules\n"
            "• Exams, hostels, fees\n"
            "• GK, UPSC & education\n"
            "• Weather, date & time"
        )
    return None

# ------------------------------------------------------
# LOAD LPU DATA (LATEST FIRST)
# ------------------------------------------------------
def load_lpu_data():
    try:
        docs = (
            db.collection("lpu_content")
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .stream()
        )

        content = ""
        for doc in docs:
            d = doc.to_dict()
            text = d.get("summary") or d.get("textContent") or ""
            title = d.get("title", "")
            content += f"{title}:\n{text}\n\n"

        return content.lower()
    except:
        return ""

# ------------------------------------------------------
# CHECK IF QUESTION IS LPU RELATED
# ------------------------------------------------------
def is_lpu_question(question: str):
    lpu_keywords = [
        "lpu", "lovely professional university", "ums",
        "hostel", "attendance", "fee", "exam",
        "mid term", "end term", "placement", "cgpa"
    ]
    q = question.lower()
    return any(k in q for k in lpu_keywords)

# ------------------------------------------------------
# CHECK IF ANSWER EXISTS IN LPU DATA
# ------------------------------------------------------
def lpu_answer_exists(question: str, lpu_data: str):
    words = [w for w in question.lower().split() if len(w) > 3]
    return any(w in lpu_data for w in words)

# ------------------------------------------------------
# GEMINI AI (UNIVERSAL)
# ------------------------------------------------------
def gemini_reply(user_message: str, lpu_context: str = ""):
    prompt = f"""
You are an EDUCATIONAL AI ASSISTANT.

STRICT RULES:
- Reply in ENGLISH ONLY.
- Answer confidently and accurately.
- If LPU context is provided, use it first.
- Never say you lack real-time access.
- Keep responses short and professional.

LPU CONTEXT (use ONLY if relevant):
{lpu_context}

USER QUESTION:
{user_message}
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return response.text.strip()
    except:
        return "Please try again in a moment."

# ------------------------------------------------------
# PROCESS MESSAGE (CORE LOGIC)
# ------------------------------------------------------
def process_message(msg: str):
    text = msg.lower().strip()

    # Greeting
    g = handle_greeting(text)
    if g:
        return g

    # Developer identity (fixed response)
    if any(k in text for k in [
        "who developed you", "who created you",
        "who made you", "your developer"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # LPU question
    if is_lpu_question(msg):
        lpu_data = load_lpu_data()
        if lpu_answer_exists(msg, lpu_data):
            return gemini_reply(msg, lpu_data)
        else:
            return gemini_reply(msg)

    # Non-LPU → Gemini directly
    return gemini_reply(msg)

# ------------------------------------------------------
# SEND WHATSAPP MESSAGE
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
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid token"

# ------------------------------------------------------
# WEBHOOK RECEIVE
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
# APP CHAT API
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    return {"reply": process_message(data.get("message", ""))}
