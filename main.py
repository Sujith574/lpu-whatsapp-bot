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
# LOAD LPU KNOWLEDGE FILE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"LPU TXT ERROR: {e}")
        return ""

# ------------------------------------------------------
# SMART SEARCH IN TXT (SEMANTIC-LIKE)
# ------------------------------------------------------
def search_lpu_txt(question: str) -> str | None:
    content = load_lpu_knowledge()
    q_words = set(question.lower().split())

    best_match = ""
    best_score = 0

    for block in content.split("\n\n"):
        block_lower = block.lower()
        score = sum(1 for w in q_words if w in block_lower)

        if score > best_score and score >= 2:
            best_score = score
            best_match = block.strip()

    return best_match if best_match else None

# ------------------------------------------------------
# SMART SEARCH IN FIRESTORE
# ------------------------------------------------------
def search_lpu_firestore(question: str) -> str | None:
    q_words = set(question.lower().split())

    try:
        docs = db.collection("lpu_content").stream()

        best_match = ""
        best_score = 0

        for doc in docs:
            d = doc.to_dict()
            text = (d.get("textContent") or "").lower()
            title = (d.get("title") or "").lower()
            keywords = " ".join(d.get("keywords", [])).lower()

            combined = f"{title} {text} {keywords}"

            score = sum(1 for w in q_words if w in combined)

            if score > best_score and score >= 2:
                best_score = score
                best_match = d.get("textContent")

        return best_match if best_match else None

    except Exception as e:
        logging.error(f"FIRESTORE SEARCH ERROR: {e}")
        return None

# ------------------------------------------------------
# GEMINI (FINAL FALLBACK)
# ------------------------------------------------------
def gemini_reply(question: str) -> str:
    prompt = f"""
You are an intelligent educational assistant.

Rules:
- Reply ONLY in English
- Be clear, confident, and accurate
- Answer naturally like a human tutor

Question:
{question}
"""
    try:
        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return res.text.strip()
    except Exception:
        return "The service is temporarily unavailable."

# ------------------------------------------------------
# MESSAGE PROCESSOR (UNIVERSAL LOGIC)
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # Greeting
    if any(w in text for w in ["hi", "hello", "hey", "hii", "hai", "namaste"]):
        return (
            "Hello! 👋\n\n"
            "You can ask about:\n"
            "• LPU exams, attendance, hostels, fees\n"
            "• Education, GK, UPSC\n"
            "• Weather, date & time"
        )

    # Developer info (allowed hard-code)
    if "who developed you" in text or "who created you" in text:
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # --------------------------------------------------
    # 1️⃣ SEARCH LPU TXT
    # --------------------------------------------------
    txt_answer = search_lpu_txt(msg)
    if txt_answer:
        return txt_answer

    # --------------------------------------------------
    # 2️⃣ SEARCH FIRESTORE
    # --------------------------------------------------
    fs_answer = search_lpu_firestore(msg)
    if fs_answer:
        return fs_answer

    # --------------------------------------------------
    # 3️⃣ GEMINI FINAL FALLBACK
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
# WHATSAPP WEBHOOK
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
