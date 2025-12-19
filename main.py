from fastapi import FastAPI, Request
import os
import logging
import requests
from google.cloud import firestore
from google import genai
from datetime import datetime
import pytz

# ------------------------------------------------------
# GOOGLE CREDENTIALS (Render-safe)
# ------------------------------------------------------
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS", "/etc/secrets/serviceAccountKey.json"
)

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
# ENV (WHATSAPP)
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
            return f.read().lower()
    except:
        return ""

STATIC_LPU = load_lpu_knowledge()

# ------------------------------------------------------
# LOAD ADMIN CONTENT (FIRESTORE)
# ------------------------------------------------------
def load_admin_lpu_content():
    try:
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
            if body:
                content += f"{d.get('title','')}:\n{body}\n\n"

        return content.lower()
    except Exception as e:
        logging.error(e)
        return ""

# ------------------------------------------------------
# GREETING
# ------------------------------------------------------
def handle_greeting(text: str):
    if text in ["hi", "hello", "hey", "hii", "hai"]:
        return (
            "Hello! 👋\n\n"
            "You can ask about:\n"
            "• LPU exams, attendance, hostels, fees\n"
            "• Education, GK, UPSC\n"
            "• Weather, date & time"
        )
    return None

# ------------------------------------------------------
# GEMINI FALLBACK
# ------------------------------------------------------
def gemini_reply(question: str, context: str = ""):
    prompt = f"""
Answer clearly and professionally in English.

If LPU context is provided, use ONLY that.
Never mention sources or say you lack access.

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
# CORE MESSAGE LOGIC (LPU → GEMINI)
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # Greeting
    greet = handle_greeting(text)
    if greet:
        return greet

    # Identity
    if "who developed you" in text or "creator" in text:
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # Creators
    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, developer, and author. "
            "He is the co-creator of the LPU Vertosewa AI Assistant."
        )

    if "vennela barnana" in text:
        return (
            "Vennela Barnana is an author and researcher, "
            "and co-creator of the LPU Vertosewa AI Assistant."
        )

    # LPU-first logic
    lpu_admin = load_admin_lpu_content()
    if any(k in text for k in ["lpu", "ums", "rms", "exam", "hostel", "fees"]):
        context = STATIC_LPU + "\n\n" + lpu_admin
        if context.strip():
            return gemini_reply(msg, context)

    # Fallback Gemini
    return gemini_reply(msg)

# ------------------------------------------------------
# WHATSAPP SEND
# ------------------------------------------------------
def send_whatsapp(to: str, text: str):
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
# WEBHOOK VERIFY (REQUIRED)
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
