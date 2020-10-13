from sanic import Sanic
from functools import wraps
from sanic.exceptions import abort
from sanic.response import json
from sanic import response

app = Sanic(__name__)

VERIFY_TOKEN = ""


def certification_verification(request):
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return True
    else:
        return False


def authorized():
    def decorator(f):
        @wraps(f)
        async def decorated_function(request, *args, **kwargs):
            is_authorized = certification_verification(request)
            if is_authorized:
                response = await f(request, *args, **kwargs)
                return response
            else:
                return json({"status": 403, "message": "not_authorized"}, 403)

        return decorated_function

    return decorator


@app.get("/webhook")
@authorized()
async def _verify_webhook(request):
    challenge = request.args.get("hub.challenge")

    if not challenge:
        return abort(400)

    return response.text(challenge)


@app.post("/webhook")
async def _webhook(request):
    page = request.json.get("object")
    entry = request.json.get("entry")

    if page == "page":
        for messaging in entry:
            webhook_event = messaging["messaging"][0]["message"]
            print(webhook_event)
            return json({"status": 200})

    else:
        return abort(404)


if __name__ == "__main__":
    app.run("0.0.0.0", 8000)
