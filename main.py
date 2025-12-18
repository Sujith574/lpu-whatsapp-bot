from fastapi import FastAPI, Request
import os
import logging
from google.cloud import firestore
from google import genai
from datetime import datetime
import pytz

# ------------------------------------------------------
# GOOGLE CREDENTIALS (Render / Local safe)
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
# FIRESTORE INIT
# ------------------------------------------------------
db = firestore.Client()

# ------------------------------------------------------
# LOAD STATIC LPU KNOWLEDGE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read().lower()
    except:
        return ""

STATIC_LPU_KNOWLEDGE = load_lpu_knowledge()

# ------------------------------------------------------
# LOAD ADMIN CONTENT (LATEST FIRST)
# ------------------------------------------------------
def load_admin_lpu_content():
    try:
        docs = (
            db.collection("lpu_content")
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .limit(25)
            .stream()
        )

        content = ""
        for doc in docs:
            d = doc.to_dict()
            body = d.get("summary") or d.get("textContent") or ""
            if body:
                content += f"{d.get('title','')}:\n{body}\n\n"

        return content.lower()

    except Exception as e:
        logging.error(f"Firestore error: {e}")
        return ""

# ------------------------------------------------------
# LPU QUESTION DETECTION
# ------------------------------------------------------
def is_lpu_question(msg: str) -> bool:
    keywords = [
        "lpu", "lovely professional university", "ums", "rms",
        "attendance", "exam", "hostel", "fee", "fees",
        "placement", "semester", "registration",
        "reappear", "mid term", "end term"
    ]
    msg = msg.lower()
    return any(k in msg for k in keywords)

# ------------------------------------------------------
# SEARCH LPU KNOWLEDGE
# ------------------------------------------------------
def find_lpu_answer(question: str):
    q = question.lower()
    if q in STATIC_LPU_KNOWLEDGE:
        return STATIC_LPU_KNOWLEDGE
    admin_data = load_admin_lpu_content()
    if any(word in admin_data for word in q.split()):
        return admin_data
    return ""

# ------------------------------------------------------
# GEMINI RESPONSE (FALLBACK ONLY)
# ------------------------------------------------------
def gemini_reply(question: str, context: str = ""):
    prompt = f"""
You are an Educational AI Assistant.

RULES:
- Reply ONLY in English
- Be short, clear, professional
- If LPU context is provided, use ONLY that
- Never say you lack real-time access

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
        return "Please try again."

# ------------------------------------------------------
# MESSAGE PROCESSOR (FINAL LOGIC)
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.lower().strip()

    # 1️⃣ Greeting
    greeting = handle_greeting(text)
    if greeting:
        return greeting

    # 2️⃣ Bot identity (highest priority)
    if any(k in text for k in [
        "who developed you", "who created you", "who made you",
        "your developer", "your creator", "founder of this bot",
        "who built you"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # 3️⃣ Creator details
    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, software developer, and author. "
            "He is the co-creator of the LPU Vertosewa AI Assistant and "
            "co-author of the book 'Decode the Code'."
        )

    if "vennela barnana" in text or "vennela" in text:
        return (
            "Vennela Barnana is an author and researcher. "
            "She is the co-creator of the LPU Vertosewa AI Assistant and "
            "co-author of the book 'Decode the Code', working on "
            "AI-driven educational initiatives."
        )

    # 4️⃣ LPU QUESTIONS → STRICT LPU FIRST
    if is_lpu_question(msg):
        lpu_answer = load_admin_lpu_content()

        if lpu_answer.strip():
            # Gemini is ONLY allowed to use LPU data here
            return gemini_reply(
                msg,
                f"Answer strictly from the following verified LPU information:\n{lpu_answer}"
            )

        # No LPU data found → Gemini fallback
        return gemini_reply(msg)

    # 5️⃣ EVERYTHING ELSE → GEMINI ONLY
    # (UPSC, GK, people, weather, date, time, general education)
    return gemini_reply(msg)
# ------------------------------------------------------
# CHAT API (FLUTTER + WEB)
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    message = data.get("message", "")
    return {"reply": process_message(message)}

