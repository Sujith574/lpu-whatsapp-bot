from fastapi import FastAPI, Request
import requests
import os
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------
# ENV VARIABLES
# ------------------------------------------------------
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sujith_token_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# ------------------------------------------------------
# LOAD KNOWLEDGE BASE FILE
# ------------------------------------------------------
def load_knowledge():
    try:
        with open("lpu_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "Knowledge base not found."

LPU_DATA = load_knowledge()


# ------------------------------------------------------
# RULE-BASED REPLIES
# ------------------------------------------------------
def rule_based(text):
    t = text.lower()

    rules = {
        "attendance": "Minimum 75% attendance required. Below that is SOA (Shortage of Attendance).",
        "soa": "SOA = Shortage of Attendance (below 75%).",
        "hostel": "Hostel timings → Girls: 10 PM, Boys: 11 PM.",
        "timing": "Hostel timings → Girls: 10 PM, Boys: 11 PM.",
        "gate pass": "Gate Pass must be applied through UMS to exit campus.",
        "night out": "Night-out requires parent approval + warden permission.",
        "reappear": "Reappear fee is ₹500 per course. Only end-term marks are replaced.",
        "cgpa": "CGPA = Σ(Credit × Grade Point) / ΣCredits.",
        "uniform": "Formal uniform mandatory Mon–Fri. Casual allowed Sat–Sun.",
        "dress": "Formal uniform mandatory Mon–Fri. Casual allowed Sat–Sun.",
        "fee": "Late fee approx ₹100/day. No admit card if fees pending.",
        "library": "Silence mandatory. Late return of books is not allowed.",
        "medical": "Visit University Hospital for medical attendance.",
        "grievance": "Submit grievance via UMS → RMS (Relationship Management System).",
    }

    for key in rules:
        if key in t:
            return rules[key]

    return None


# ------------------------------------------------------
# AI REPLY FUNCTION
# ------------------------------------------------------
def ai_reply(user_message):
    if not GROQ_API_KEY:
        return "AI backend is not configured."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are the official AI Assistant for Lovely Professional University (LPU).\n"
        "Use the following knowledge base to answer questions accurately.\n"
        "If the user asks something outside the knowledge base, answer politely using general knowledge.\n\n"
        f"LPU KNOWLEDGE BASE:\n{LPU_DATA}\n\n"
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2
    }

    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20)
        data = response.json()
        logging.info(data)

        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        if "error" in data:
            return f"Groq Error: {data['error'].get('message', 'Unknown error')}"

        return "Unexpected AI response."

    except Exception as e:
        logging.error(f"AI ERROR: {e}")
        return "AI is facing issues. Please try again later."


# ------------------------------------------------------
# SEND MESSAGE TO WHATSAPP
# ------------------------------------------------------
def send_message(to, text):
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": text}
    }

    try:
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        logging.error(f"Send message error: {e}")


# ------------------------------------------------------
# WEBHOOK VERIFICATION
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"


# ------------------------------------------------------
# RECEIVE MESSAGE
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        entry = data["entry"][0]
        message = entry["changes"][0]["value"].get("messages", [])[0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")

    except:
        return {"status": "ignored"}

    # WELCOME MESSAGE
    if text.lower() in ["hi", "hello", "hey", "menu", "start"]:
        welcome = (
            "👋 Hello! I am your *LPU Assistant Bot*.\n\n"
            "Ask me anything about:\n"
            "• Attendance rules\n"
            "• Hostel timings\n"
            "• Reappear & exam rules\n"
            "• CGPA calculation\n"
            "• Fees & fines\n"
            "• Dress code\n"
            "• LPU regulations\n"
            "• Academic processes\n\n"
            "How can I help you today? 😊"
        )
        send_message(sender, welcome)
        return {"status": "ok"}

    # RULE-BASED REPLY
    rb = rule_based(text)
    if rb:
        send_message(sender, rb)
        return {"status": "ok"}

    # AI FALLBACK
    reply = ai_reply(text)
    send_message(sender, reply)

    return {"status": "ok"}
