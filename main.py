from fastapi import FastAPI, Request
import requests
import os
import logging
import datetime
import pytz

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ENV
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lpu_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.1-8b-instant"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Creator message
CREATOR_MESSAGE = (
    "I was specially designed for Lovely Professional University. "
    "I was developed by Vennela Barnana."
)

# ---------------- LOAD SECTIONS ----------------
def load_sections():
    folder = "sections"
    data = {}

    if not os.path.exists(folder):
        return data

    for f in os.listdir(folder):
        if f.endswith(".txt"):
            try:
                with open(os.path.join(folder, f), "r", encoding="utf-8") as file:
                    key = f.replace(".txt", "")
                    data[key] = file.read().strip()
            except:
                continue
    return data


SECTIONS = load_sections()


# ---------------- RULE-BASED LPU DETECTION ----------------
def find_lpu_answer(text):
    t = text.lower()

    # Creator
    if "who created" in t or "who developed" in t or "developer" in t or "founder" in t:
        return CREATOR_MESSAGE

    # High priority rules
    keyword_map = {
        "attendance": "attendance",
        "cgpa": "cgpa",
        "mess": "mess_rules",
        "hostel": "hostel_rules",
        "leave": "hostel_leave_rules",
        "visitor": "visitor_rules",
        "parking": "parking",
        "rfid": "rfid_and_parking_rules",
        "wifi": "wifi_network",
        "exam": "exam_rules",
        "reappear": "exam_reappear",
        "library": "library",
        "medical": "medical",
        "security": "security_and_safety",
        "rm system": "rm_system"
    }

    for word, section in keyword_map.items():
        if word in t and section in SECTIONS:
            return SECTIONS[section]

    # Filename-based match
    for key, content in SECTIONS.items():
        if key.replace("_", " ") in t:
            return content

    return None


# ---------------- EDUCATIONAL DETECTOR ----------------
def is_educational(text):
    words = ["study", "learn", "what is", "define", "explain", "science", "python",
             "java", "maths", "history", "biology", "chemistry", "engineering",
             "project", "exam", "assignment", "education", "college"]
    return any(w in text.lower() for w in words)


# ---------------- AI HANDLER ----------------
def ai_answer(text):
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Answer educational questions briefly and clearly."},
            {"role": "user", "content": text}
        ],
        "temperature": 0.2
    }

    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          json=payload, headers=headers).json()
        return r["choices"][0]["message"]["content"]
    except:
        return "AI is unavailable at the moment."


# ---------------- SEND MESSAGE ----------------
def send_message(to, body):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}",
               "Content-Type": "application/json"}

    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": body}}
    try:
        requests.post(url, json=payload)
    except:
        pass


# ---------------- WEBHOOK VERIFY ----------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid token"


# ---------------- MAIN WEBHOOK ----------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = msg["from"]
        text = msg["text"]["body"].strip()
    except:
        return {"status": "ignored"}

    low = text.lower()

    # Greetings
    if low in ["hi", "hello", "hey", "start", "menu"]:
        send_message(sender,
                     "👋 Hello! I am the official *LPU Assistant Bot*.\n"
                     "I was specially designed only for Lovely Professional University.\n\n"
                     "Ask me anything related to:\n"
                     "• Attendance\n"
                     "• Hostel & Mess\n"
                     "• Exams & CGPA\n"
                     "• Visitor pass / RFID / Security\n"
                     "• Fees / Placements / Transport\n\n"
                     "I can also answer *educational questions*. 🚀")
        return {"status": "ok"}

    # LPU rule-based
    ans = find_lpu_answer(low)
    if ans:
        send_message(sender, ans)
        return {"status": "ok"}

    # Educational Q
    if is_educational(text):
        send_message(sender, ai_answer(text))
        return {"status": "ok"}

    # Reject Non-LPU + Non-Educational
    send_message(sender,
                 "I can answer only educational or LPU-related questions.")
    return {"status": "ok"}
