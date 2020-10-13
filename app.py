import os

import aiohttp

import neispy

from sanic import Sanic
from sanic import response
from sanic.exceptions import abort

app = Sanic(__name__)

PAGE_ACCESS_TOKEN = os.environ["PAGE_ACCESS_TOKEN"]


async def call_send_api(sender_psid, response):
    request_body = {"recipient": {"id": sender_psid}, "message": response}
    qs = {"access_token": PAGE_ACCESS_TOKEN}
    try:
        async with aiohttp.ClientSession() as cs:
            async with cs.post(
                "https://graph.facebook.com/v2.6/me/messages",
                json=request_body,
                params=qs,
            ) as r:
                print("message sent")
    except Exception as err:
        print("Unable to send message:" + err)


async def handle_message(sender_psid, received_message):
    if received_message.get("text"):
        response = {
            "text": f"""You sent the message: "{received_message["text"]}". Now send me an attachment!"""
        }
    await call_send_api(sender_psid, response)


@app.listener("before_server_start")
async def init_neispy_client(app, loop):
    app.neispy = neispy.Client()


@app.get("/webhook")
async def _verify_webhook(request):
    VERIFY_TOKEN = "<YOUR_VERIFY_TOKEN>"
    challenge = request.args.get("hub.challenge")
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return response.text(challenge)
        else:
            return abort(403)


@app.post("/webhook")
async def _webhook(request):
    body = request.json
    if body.get("object") == "page":
        for messaging in body.get("entry"):
            webhook_event = messaging["messaging"][0]
            sender_psid = webhook_event["sender"]["id"]
            if webhook_event.get("message"):
                await handle_message(sender_psid, webhook_event["message"])

            return response.text("EVENT_RECEIVED")
    else:
        return abort(404)


if __name__ == "__main__":
    app.run("0.0.0.0", 8000)