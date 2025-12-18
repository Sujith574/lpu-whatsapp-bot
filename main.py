from fastapi import FastAPI, Request
import os
import logging
import requests
from google.cloud import firestore
from google import genai
from difflib import SequenceMatcher

# ------------------------------------------------------
# GOOGLE CREDENTIALS (Render compatible)
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
# ENV (WhatsApp)
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
# LOAD ADMIN CONTENT
# ------------------------------------------------------
def load_admin_lpu_content():
    try:
        docs = (
            db.collection("lpu_content")
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .limit(25)
            .stream()
        )

        blocks = []
        for doc in docs:
            d = doc.to_dict()
            body = d.get("summary") or d.get("textContent") or ""
            if body:
                blocks.append(f"{d.get('title','')}:\n{body}")

        return "\n\n".join(blocks)

    except Exception as e:
        logging.error(e)
        return ""

# ------------------------------------------------------
# GREETING
# ------------------------------------------------------
def handle_greeting(text):
    greetings = ["hi", "hello", "hey", "hii", "hai", "namaste"]
    if text in greetings or any(g in text for g in greetings):
        return (
            "Hello! 👋\n\n"
            "You can ask me about:\n"
            "• LPU academics & notices\n"
            "• Exams, hostels, fees, attendance\n"
            "• UPSC, GK, education\n"
            "• Weather, date & time"
        )
    return None

# ------------------------------------------------------
# LPU QUESTION CHECK
# ------------------------------------------------------
def is_lpu_question(text):
    keywords = [
        "lpu", "lovely professional university", "ums", "rms",
        "attendance", "exam", "hostel", "fee", "fees",
        "placement", "semester", "registration",
        "reappear", "mid term", "end term"
    ]
    return any(k in text for k in keywords)

# ------------------------------------------------------
# SMART LPU MATCHING
# ------------------------------------------------------
def find_lpu_answer(question):
    combined = STATIC_LPU + "\n" + load_admin_lpu_content()
    question = question.lower()

    best, score = "", 0
    for para in combined.split("\n\n"):
        s = SequenceMatcher(None, question, para.lower()).ratio()
        if s > score:
            score = s
            best = para

    return best if score > 0.35 else ""

# ------------------------------------------------------
# GEMINI FALLBACK
# ------------------------------------------------------
def gemini_reply(question):
    prompt = f"""
You are an educational AI assistant.

Rules:
- Reply ONLY in English
- Be short, accurate, professional
- Never mention limitations or sources

Question:
{question}
"""
    try:
        r = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return r.text.strip()
    except Exception as e:
        logging.error(e)
        return "Please try again."

# ------------------------------------------------------
# CORE LOGIC
# ------------------------------------------------------
def process_message(msg):
    text = msg.lower().strip()

    g = handle_greeting(text)
    if g:
        return g

    if any(k in text for k in [
        "who developed you", "who created you", "who made you", "who built you"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    if "sujith lavudu" in text:
        return (
            "Sujith Lavudu is a student innovator, software developer, and author. "
            "He is the co-creator of the LPU Vertosewa AI Assistant."
        )

    if "vennela barnana" in text or "vennela" in text:
        return (
            "Vennela Barnana is an author and researcher, and the co-creator "
            "of the LPU Vertosewa AI Assistant."
        )

    if is_lpu_question(text):
        ans = find_lpu_answer(text)
        if ans:
            return ans

    return gemini_reply(msg)

# ------------------------------------------------------
# CHAT API (Flutter)
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    return {"reply": process_message(data.get("message", ""))}

# ------------------------------------------------------
# WHATSAPP VERIFY
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    p = dict(request.query_params)
    if p.get("hub.verify_token") == VERIFY_TOKEN:
        return int(p.get("hub.challenge"))
    return "Invalid token"

# ------------------------------------------------------
# WHATSAPP RECEIVE
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return {"status": "ignored"}

        msg = value["messages"][0]
        sender = msg["from"]
        text = msg["text"]["body"]

        reply = process_message(text)

        requests.post(
            f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages",
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": sender,
                "type": "text",
                "text": {"body": reply},
            },
        )

    except Exception as e:
        logging.error(e)

    return {"status": "ok"}
