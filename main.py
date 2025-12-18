from fastapi import FastAPI, Request
import requests
import os
import logging
from google.cloud import firestore
from google import genai

# ------------------------------------------------------
# REQUIRED: FIRESTORE CREDENTIALS
# ------------------------------------------------------
# Make sure serviceAccountKey.json exists in project root
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json"
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
# FIRESTORE INIT
# ------------------------------------------------------
db = firestore.Client()

# ------------------------------------------------------
# ENV
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# ------------------------------------------------------
# GREETING HANDLER
# ------------------------------------------------------
def handle_greeting(msg: str):
    greetings = ["hi", "hello", "hey", "hii", "hai", "namaste"]
    if msg in greetings or any(g in msg for g in greetings):
        return (
            "Hello! 👋\n\n"
            "I can assist you with:\n"
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
            .limit(20)
            .stream()
        )

        content_blocks = []
        for doc in docs:
            d = doc.to_dict()
            body = d.get("summary") or d.get("textContent") or ""
            title = d.get("title", "")
            if body:
                content_blocks.append(f"{title}:\n{body}")

        return "\n\n".join(content_blocks)

    except Exception as e:
        logging.error(f"Firestore read error: {e}")
        return ""

# ------------------------------------------------------
# CHECK IF QUESTION IS ABOUT LPU
# ------------------------------------------------------
def is_lpu_question(msg: str) -> bool:
    keywords = [
        "lpu", "lovely professional university", "ums",
        "attendance", "exam", "hostel", "fee", "fees",
        "placement", "semester", "registration",
        "reappear", "mid term", "end term"
    ]
    msg = msg.lower()
    return any(k in msg for k in keywords)

# ------------------------------------------------------
# GEMINI RESPONSE (SINGLE SOURCE FOR AI)
# ------------------------------------------------------
def gemini_reply(user_message: str, lpu_context: str = "") -> str:
    prompt = f"""
You are an Educational AI Assistant.

STRICT RULES:
- Reply ONLY in English
- Keep replies short, accurate, and professional
- If LPU data is provided, prioritize it
- Never say you lack real-time or live access
- Answer confidently and clearly

LPU DATA (if any):
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
    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return "The service is temporarily busy. Please try again."

# ------------------------------------------------------
# MESSAGE PROCESSOR (FINAL LOGIC)
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # Greeting
    greeting = handle_greeting(text)
    if greeting:
        return greeting

    # --------------------------------------------------
    # BOT IDENTITY (HIGHEST PRIORITY)
    # --------------------------------------------------
    if any(k in text for k in [
        "who developed you", "who created you", "who made you",
        "your developer", "your creator", "founder of this bot",
        "who built you"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # --------------------------------------------------
    # CREATOR DETAILS
    # --------------------------------------------------
    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, software developer, and author.\n\n"
            "He is the co-creator of the LPU Vertosewa AI Assistant and "
            "co-author of the book “Decode the Code”."
        )

    if "vennela barnana" in text or "vennela" in text:
        return (
            "Vennela Barnana is an author and researcher.\n\n"
            "She is the co-creator of the LPU Vertosewa AI Assistant and "
            "co-author of the book “Decode the Code”, working on "
            "AI-driven educational initiatives."
        )

    # --------------------------------------------------
    # LPU QUESTIONS → ADMIN DATA FIRST
    # --------------------------------------------------
    if is_lpu_question(msg):
        lpu_data = load_admin_lpu_content()
        return gemini_reply(msg, lpu_data)

    # --------------------------------------------------
    # EVERYTHING ELSE → GEMINI ONLY
    # (Weather, Date, Time, GK, UPSC, Education, People)
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
        logging.error(f"Webhook error: {e}")

    return {"status": "ok"}

# ------------------------------------------------------
# CHAT API (FLUTTER APP)
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    try:
        data = await request.json()
        user_msg = data.get("message", "")
        logging.info(f"APP MESSAGE: {user_msg}")

        reply = process_message(user_msg)
        logging.info(f"APP REPLY: {reply}")

        return {"reply": reply}

    except Exception as e:
        logging.error(f"CHAT API ERROR: {e}")
        return {"reply": "Temporary server issue. Please try again."}

