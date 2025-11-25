from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

VERIFY_TOKEN = "sujith_token_123"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


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
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        # detect if 'messages' exists in payload
        messages = value.get("messages", [])
        if messages:
            message = messages[0]
            sender = message.get("from")

            # extract text safely
            text = message.get("text", {}).get("body", "")

            reply = generate_reply(text)
            send_message(sender, reply)

    except Exception as e:
        print("Webhook Error:", e)

    return {"status": "ok"}


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
    requests.post(url, json=payload, headers=headers)



def generate_reply(text):
    if not text:
        return "I received your message!"
    return f"You said: {text}\nYour LPU Assistant bot is working!"

