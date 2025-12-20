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
# HEALTH CHECK (CLOUD RUN)
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
# FIRESTORE (LAZY INIT)
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
    except:
        return ""

STATIC_LPU = load_lpu_knowledge()

# ------------------------------------------------------
# LOAD ADMIN CONTENT (CATEGORY + KEYWORDS)
# ------------------------------------------------------
def search_admin_content(question: str):
    db = get_db()
    q = question.lower()
    matches = []

    docs = (
        db.collection("lpu_content")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(50)
        .stream()
    )

    for doc in docs:
        d = doc.to_dict()

        text = (d.get("textContent") or "").lower()
        keywords = d.get("keywords") or []
        category = (d.get("category") or "").lower()

        # Match by keyword OR category
        if any(k in q for k in keywords) or category in q:
            matches.append(
                f"{d.get('title','')}:\n{d.get('textContent','')}"
            )

    return "\n\n".join(matches)

# ------------------------------------------------------
# GREETING
# ------------------------------------------------------
def handle_greeting(text: str):
    if text in ["hi", "hello", "hey", "hii", "hai", "namaste"]:
        return (
            "Hello! 👋\n\n"
            "You can ask about:\n"
            "• LPU exams, attendance, hostels, fees\n"
            "• RMS / UMS / registrations\n"
            "• DSW notices\n"
            "• UPSC, GK, people\n"
            "• Date & time"
        )
    return None

# ------------------------------------------------------
# GEMINI RESPONSE (SAFE)
# ------------------------------------------------------
def gemini_reply(question: str, context: str = ""):
    prompt = f"""
You are an educational assistant.

Rules:
- Reply only in English
- Be accurate, professional, concise
- If LPU context is provided, use ONLY that
- Do not guess or invent facts

LPU CONTEXT:
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
        logging.error(e)
        return "Please try again later."

# ------------------------------------------------------
# CORE MESSAGE LOGIC
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # 1️⃣ FIXED PERSON IDENTITIES
    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, software developer, and author. "
            "He is the co-creator of the LPU Vertosewa AI Assistant "
            "and co-author of the book 'Decode the Code'."
        )

    if "vennela barnana" in text:
        return (
            "Vennela Barnana is an author and researcher. "
            "She is the co-creator of the LPU Vertosewa AI Assistant "
            "and co-author of the book 'Decode the Code'."
        )

    if "rashmi mittal" in text:
        return (
            "Dr. Rashmi Mittal is the Pro-Chancellor of Lovely Professional University (LPU)."
        )

    # 2️⃣ GREETING
    greet = handle_greeting(text)
    if greet:
        return greet

    # 3️⃣ DATE / TIME
    if "time" in text or "date" in text:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        return (
            f"📅 Date: {now.strftime('%d %B %Y')}\n"
            f"⏰ Time: {now.strftime('%I:%M %p')} (IST)"
        )

    # 4️⃣ BOT IDENTITY
    if any(k in text for k in [
        "who developed you", "who created you",
        "your developer", "your creator"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # 5️⃣ LPU-FIRST LOGIC
    LPU_TERMS = [
        "lpu", "lovely professional university",
        "ums", "rms", "dsw",
        "attendance", "hostel", "fees",
        "exam", "semester", "registration",
        "reappear", "mid term", "end term"
    ]

    if any(k in text for k in LPU_TERMS):
        admin_answer = search_admin_content(msg)

        if admin_answer.strip():
            return gemini_reply(msg, admin_answer)

        if STATIC_LPU.strip():
            return gemini_reply(msg, STATIC_LPU)

        return "No official LPU update is available for this query yet."

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
# WEBHOOK VERIFY
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
# WEBHOOK RECEIVE
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return {"status": "ignored"}

        msg = value["messages"][0]["text"]["body"]
        sender = value["messages"][0]["from"]

        reply = process_message(msg)
        send_whatsapp(sender, reply)

    except Exception as e:
        logging.error(e)

    return {"status": "ok"}

# ------------------------------------------------------
# FLUTTER CHAT API
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    return {"reply": process_message(data.get("message", ""))}
