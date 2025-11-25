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
GROQ_MODEL = os.getenv("GROQ_MODEL", "mixtral-8x7b")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


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

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an AI assistant for Lovely Professional University (LPU). "
                    "Always answer accurately using LPU rules, regulations, hostel timings, "
                    "attendance rules, academic guidelines, reappear rules, CGPA calculation, "
                    "fee deadlines, discipline rules, and campus policies. "
                    "If asked something non-LPU, answer politely and helpfully."
                )
            },
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=20)
        data = response.json()
        logging.info(data)

        # SUCCESS RESPONSE
        if "choices" in data:
            return data["choices"][0]["message"]["content"]

        # ERROR RESPONSE
        if "error" in data:
            return f"Groq Error: {data['error'].get('message', 'Unknown error')}"

        return "Unexpected AI response received."

    except Exception as e:
        logging.error(f"AI ERROR: {e}")
        return "Sorry, I am facing issues. Please try again."


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
# VERIFY WEBHOOK
# ------------------------------------------------------
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"


# ------------------------------------------------------
# RECEIVE MESSAGES
# ------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    logging.info(data)

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        message = messages[0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")

        # --------------------------
        # WELCOME MESSAGE
        # --------------------------
        if text.lower() in ["hi", "hello", "hey", "menu", "start"]:
            welcome_msg = (
                "👋 Hello! I am your *LPU Assistant Chatbot*.\n\n"
                "I can help you with:\n"
                "• Attendance rules\n"
                "• Exam & reappear rules\n"
                "• Hostel timings & regulations\n"
                "• CGPA calculation\n"
                "• Fee deadlines & fines\n"
                "• Discipline rules\n"
                "• Academic processes\n"
                "• Contact info (warden, academic office, etc.)\n\n"
                "Ask me anything! 😊"
            )
            send_message(sender, welcome_msg)
            return {"status": "ok"}

        # --------------------------
        # AI GENERATED REPLY
        # --------------------------
        reply = ai_reply(text)
        send_message(sender, reply)

    except Exception as e:
        logging.error(f"Webhook error: {e}")

    return {"status": "ok"}
