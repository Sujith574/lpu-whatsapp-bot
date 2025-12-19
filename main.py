from fastapi import FastAPI, Request
import os
import logging
import requests
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
# HEALTH CHECK (VERY IMPORTANT FOR CLOUD RUN)
# ------------------------------------------------------
@app.get("/")
def health():
    return {"status": "ok"}

# ------------------------------------------------------
# GEMINI CONFIG
# ------------------------------------------------------
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL = "models/gemini-2.5-flash"

# ------------------------------------------------------
# FIRESTORE (LAZY INIT — FIXES CRASH)
# ------------------------------------------------------
def get_db():
    return firestore.Client()

# ------------------------------------------------------
# WHATSAPP ENV
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# ------------------------------------------------------
# LOAD STATIC LPU KNOWLEDGE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

STATIC_LPU = load_lpu_knowledge()

# ------------------------------------------------------
# LOAD ADMIN CONTENT (FIRESTORE)
# ------------------------------------------------------
def load_admin_lpu_content():
    try:
        db = get_db()
        docs = (
            db.collection("lpu_content")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(25)
            .stream()
        )

        content = ""
        for doc in docs:
            d = doc.to_dict()
            body = d.get("textContent") or d.get("summary") or ""
            title = d.get("title", "")
            if body:
                content += f"{title}:\n{body}\n\n"

        return content
    except Exception as e:
        logging.error(f"Firestore error: {e}")
        return ""

# ------------------------------------------------------
# GREETING
# ------------------------------------------------------
def handle_greeting(text: str):
    if text in ["hi", "hello", "hey", "hii", "hai", "namaste"]:
        return (
            "Hello! 👋\n\n"
            "You can ask about:\n"
            "• LPU exams, attendance, hostels, fees\n"
            "• RMS, UMS, registrations\n"
            "• UPSC, GK, people\n"
            "• Date & time"
        )
    return None

# ------------------------------------------------------
# GEMINI RESPONSE
# ------------------------------------------------------
def gemini_reply(question: str, context: str = ""):
    prompt = f"""
You are an intelligent educational assistant.

Rules:
- Reply only in English
- Be clear, accurate, and professional
- If LPU context is given, prioritize it
- Never say information is unavailable

LPU CONTEXT (if any):
{context}

QUESTION:
{question}
"""
    try:
        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return res.text.strip()
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return "Please try again later."

# ------------------------------------------------------
# CORE MESSAGE LOGIC
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # 1️⃣ FIXED IDENTITY RESPONSES (TOP PRIORITY)
    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, software developer, and author. "
            "He is the co-creator of the LPU Vertosewa AI Assistant "
            "and co-author of the book 'Decode the Code'."
        )

    if "vennela barnana" in text or "vennela" in text:
        return (
            "Vennela Barnana is an author and researcher. "
            "She is the co-creator of the LPU Vertosewa AI Assistant "
            "and co-author of the book 'Decode the Code'."
        )

    # 2️⃣ GREETING
    greet = handle_greeting(text)
    if greet:
        return greet

    # 3️⃣ DATE / TIME
    if "time" in text or "date" in text:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        return f"📅 Date: {now.strftime('%d %B %Y')}\n⏰ Time: {now.strftime('%I:%M %p')} (IST)"

    # 4️⃣ BOT IDENTITY
    if any(k in text for k in ["who developed you", "who created you", "your creator", "your developer"]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # 5️⃣ LPU QUESTIONS
    LPU_KEYWORDS = [
        "lpu", "lovely professional university",
        "ums", "rms",
        "attendance", "hostel", "fee", "fees",
        "semester", "registration",
        "reappear", "mid term", "end term"
    ]

    if any(k in text for k in LPU_KEYWORDS):
        admin_data = load_admin_lpu_content()
        context = STATIC_LPU + "\n\n" + admin_data
        return gemini_reply(msg, context)

    # 6️⃣ EVERYTHING ELSE → GEMINI
    return gemini_reply(msg)

# ------------------------------------------------------
# SEND WHATSAPP MESSAGE
# ------------------------------------------------------
def send_whatsapp(to: str, text: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        return

    requests.post(
        f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages",
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
# WEBHOOK VERIFY (META)
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = request.query_params

    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == VERIFY_TOKEN
    ):
        return int(params.get("hub.challenge"))

    return {"error": "Invalid token"}

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

        message = value["messages"][0]["text"]["body"]
        sender = value["messages"][0]["from"]

        reply = process_message(message)
        send_whatsapp(sender, reply)

    except Exception as e:
        logging.error(f"Webhook error: {e}")

    return {"status": "ok"}

# ------------------------------------------------------
# FLUTTER CHAT API
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    return {"reply": process_message(data.get("message", ""))}

