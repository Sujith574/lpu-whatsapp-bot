from fastapi import FastAPI, Request
import os
import logging
from datetime import datetime
import pytz
from google.cloud import firestore
from google import genai

# ------------------------------------------------------
# GOOGLE CREDENTIALS
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
# LOAD STATIC LPU KNOWLEDGE
# ------------------------------------------------------
def load_lpu_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

STATIC_LPU_KNOWLEDGE = load_lpu_knowledge()

# ------------------------------------------------------
# LOAD ADMIN CONTENT
# ------------------------------------------------------
def load_admin_lpu_content():
    content = ""
    try:
        docs = db.collection("lpu_content").stream()
        for doc in docs:
            d = doc.to_dict()
            body = d.get("summary") or d.get("textContent") or ""
            if body:
                content += body + "\n"
    except Exception as e:
        logging.error(e)
    return content

# ------------------------------------------------------
# SMART LPU SEARCH
# ------------------------------------------------------
def search_lpu_sources(question: str) -> str:
    q = question.lower()

    # 1️⃣ Search static knowledge
    for line in STATIC_LPU_KNOWLEDGE.split("\n"):
        if any(word in line.lower() for word in q.split()):
            return line

    # 2️⃣ Search admin uploads
    admin_data = load_admin_lpu_content()
    for line in admin_data.split("\n"):
        if any(word in line.lower() for word in q.split()):
            return line

    return ""

# ------------------------------------------------------
# GEMINI FALLBACK
# ------------------------------------------------------
def gemini_reply(question: str):
    prompt = f"""
Answer the following question clearly and professionally.

Question:
{question}
"""
    try:
        res = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return res.text.strip()
    except:
        return "Temporary service issue. Please try again."

# ------------------------------------------------------
# MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(msg: str) -> str:
    text = msg.strip()

    # Greeting
    if text.lower() in ["hi", "hello", "hey", "hii", "hai"]:
        return (
            "Hello! 👋\n\n"
            "You can ask about:\n"
            "• LPU exams, RMS, UMS, hostels, fees\n"
            "• Education, GK, UPSC\n"
            "• Date, time, weather"
        )

    # Date & Time
    if "time" in text.lower():
        return datetime.now(pytz.timezone("Asia/Kolkata")).strftime("Time: %I:%M %p")

    if "date" in text.lower():
        return datetime.now(pytz.timezone("Asia/Kolkata")).strftime("Date: %d %B %Y")

    # Creator info
    if "sujith lavudu" in text.lower():
        return (
            "Sujith Lavudu is a student innovator, software developer, "
            "co-creator of LPU Vertosewa AI Assistant, and co-author of "
            "the book 'Decode the Code'."
        )

    if "vennela barnana" in text.lower():
        return (
            "Vennela Barnana is an author and researcher, co-creator of "
            "LPU Vertosewa AI Assistant, and co-author of 'Decode the Code'."
        )

    # 🔴 LPU FIRST (STRICT)
    lpu_answer = search_lpu_sources(text)
    if lpu_answer:
        return lpu_answer

    # 🔵 Gemini fallback (UPSC, GK, people, general)
    return gemini_reply(text)

# ------------------------------------------------------
# CHAT API (FLUTTER APP)
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    msg = data.get("message", "")
    reply = process_message(msg)
    return {"reply": reply}
