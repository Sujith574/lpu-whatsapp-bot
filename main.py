from fastapi import FastAPI, Request
import requests
import os
import logging
from google.cloud import firestore
from google import genai

# ------------------------------------------------------
# FIRESTORE AUTH
# ------------------------------------------------------
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json"
)

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
def handle_greeting(msg: str):
    if any(w in msg for w in ["hi", "hello", "hey", "hii", "hai", "namaste"]):
        return (
            "Hello! 👋\n\n"
            "You can ask about:\n"
            "• LPU exams, attendance, hostels, fees\n"
            "• Education, GK, UPSC\n"
            "• Weather, date & time"
        )
    return None

# ------------------------------------------------------
# SEARCH LPU DATABASE (STRICT FIRST)
# ------------------------------------------------------
def search_lpu_database(question: str) -> str | None:
    try:
        q = question.lower()

        docs = db.collection("lpu_content").stream()
        for doc in docs:
            d = doc.to_dict()
            text = (d.get("textContent") or "").lower()
            title = (d.get("title") or "").lower()
            keywords = [k.lower() for k in d.get("keywords", [])]

            # keyword OR text match
            if any(k in q for k in keywords) or q in text or q in title:
                return d.get("textContent")

        return None

    except Exception as e:
        logging.error(f"LPU SEARCH ERROR: {e}")
        return None

# ------------------------------------------------------
# GEMINI FALLBACK
# ------------------------------------------------------
def gemini_reply(user_message: str) -> str:
    prompt = f"""
You are an Educational AI Assistant.

RULES:
- Reply ONLY in English
- Keep replies short & professional
- Never mention limitations
- Answer clearly

QUESTION:
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
        return "The service is temporarily busy."

# ------------------------------------------------------
# MESSAGE PROCESSOR (FINAL)
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # Greeting
    greeting = handle_greeting(text)
    if greeting:
        return greeting

    # Identity (hard-coded)
    if "who developed you" in text:
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # RMS FIX (HARDCODED — GUARANTEED)
    if "rms" in text:
        return (
            "At LPU, RMS stands for **Relationship Management System**. "
            "It is used to manage student queries and institutional communication."
        )

    # --------------------------------------------------
    # LPU DATABASE → FIRST PRIORITY
    # --------------------------------------------------
    lpu_answer = search_lpu_database(text)
    if lpu_answer:
        return lpu_answer

    # --------------------------------------------------
    # GEMINI → ONLY IF NOT FOUND
    # --------------------------------------------------
    return gemini_reply(msg)

# ------------------------------------------------------
# WHATSAPP SEND
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
# WHATSAPP RECEIVE
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        reply = process_message(msg["text"]["body"])
        send_message(msg["from"], reply)
    except Exception as e:
        logging.error(e)
    return {"status": "ok"}

# ------------------------------------------------------
# FLUTTER CHAT API
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    reply = process_message(data.get("message", ""))
    return {"reply": reply}
