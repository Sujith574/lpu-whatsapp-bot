from fastapi import FastAPI, Request
import requests
import os
app = FastAPI()
VERIFY_TOKEN = "sujith_token_123"              # keep this same
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")   # we will set this on Render
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID") # set this on Render
@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return "Invalid verify token"
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")
        reply = generate_reply(text)
        send_message(sender, reply)
    except Exception:
        pass
    return {"status": "ok"}
def send_message(to, text):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": text}
    }
    requests.post(url, json=payload, headers=headers)
def generate_reply(text):
    if not text:
        return "I received your message."
    return f"You said: {text}\nYour LPU Assistant bot is working!"