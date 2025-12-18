from fastapi import FastAPI, Request
import os
import logging
from google.cloud import firestore
from google import genai
from difflib import SequenceMatcher

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
# FIRESTORE INIT
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

STATIC_LPU = load_lpu_knowledge()

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
def handle_greeting(text: str):
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
# LPU QUESTION DETECTION
# ------------------------------------------------------
def is_lpu_question(text: str):
    keywords = [
        "lpu", "lovely professional university", "ums", "rms",
        "attendance", "exam", "hostel", "fee", "fees",
        "placement", "semester", "registration",
        "reappear", "mid term", "end term"
    ]
    return any(k in text for k in keywords)

# ------------------------------------------------------
# SMART LPU ANSWER MATCHING
# ------------------------------------------------------
def find_lpu_answer(question: str):
    combined = STATIC_LPU + "\n" + load_admin_lpu_content()
    question = question.lower()

    best_match = ""
    best_score = 0

    for para in combined.split("\n\n"):
        score = SequenceMatcher(None, question, para.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = para

    if best_score > 0.35:  # similarity threshold
        return best_match.strip()

    return ""

# ------------------------------------------------------
# GEMINI FALLBACK
# ------------------------------------------------------
def gemini_reply(question: str):
    prompt = f"""
You are an educational AI assistant.

Rules:
- Reply ONLY in English
- Be short, accurate, professional
- Never mention data sources or limitations

Question:
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
# MESSAGE PROCESSOR
# ------------------------------------------------------
def process_message(msg: str):
    text = msg.lower().strip()

    # Greeting
    greeting = handle_greeting(text)
    if greeting:
        return greeting

    # Identity
    if any(k in text for k in [
        "who developed you", "who created you", "who made you",
        "who built you", "your developer"
    ]):
        return (
            "I was developed by Sujith Lavudu and Vennela Barnana "
            "for Lovely Professional University (LPU)."
        )

    # Creator details
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
            "co-author of the book 'Decode the Code'."
        )

    # LPU FIRST
    if is_lpu_question(text):
        lpu_answer = find_lpu_answer(text)
        if lpu_answer:
            return lpu_answer

    # Gemini fallback
    return gemini_reply(msg)

# ------------------------------------------------------
# CHAT API
# ------------------------------------------------------
@app.post("/chat")
async def chat_api(request: Request):
    data = await request.json()
    return {"reply": process_message(data.get("message", ""))}
