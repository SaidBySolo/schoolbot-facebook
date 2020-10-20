import asyncio
import os
from typing import Union

import aiohttp

import aiocache

import neispy
from neispy.error import DataNotFound

from sanic import Sanic
from sanic import response
from sanic.exceptions import abort

app: Sanic = Sanic(__name__)

PAGE_ACCESS_TOKEN: str = os.environ["PAGE_ACCESS_TOKEN"]


async def call_send_api(sender_psid: str, response: dict) -> None:
    request_body: dict = {"recipient": {"id": sender_psid}, "message": response}
    qs: dict = {"access_token": PAGE_ACCESS_TOKEN}
    try:
        async with aiohttp.ClientSession() as cs:
            async with cs.post(
                "https://graph.facebook.com/v2.6/me/messages",
                json=request_body,
                params=qs,
            ) as r:
                if r.status != 200:
                    print("Unable to send message:" + str(await r.json()))

                print("message sent")
    except Exception as err:
        print("Unable to send message:" + err)


async def get_code(schoolname: str, neispy_client: neispy.Client) -> Union[list, None]:
    try:
        school_info: list = await neispy_client.schoolInfo(SCHUL_NM=schoolname)
    except DataNotFound:
        return
    else:
        return school_info


async def check_result(
    school_name: str, neispy_client: neispy.Client()
) -> Union[None, list, tuple]:
    info = await get_code(school_name, neispy_client)

    if not info:
        return

    if len(info) > 1:
        return info
    else:
        return info[0].ATPT_OFCDC_SC_CODE, info[0].SD_SCHUL_CODE


async def get_meal(ae: str, se: str, client: neispy.Client) -> str:
    scmeal: str = await client.mealServiceDietInfo(ae, se, MLSV_YMD=20201019)
    meal: str = scmeal[0].DDISH_NM.replace("<br/>", "\n")
    return meal


async def wait_for_user_choice(cache_client: aiocache.Cache, psid: str) -> None:
    while True:
        await asyncio.sleep(0.5)
        if not await cache_client.exists(psid):
            return


async def timeout(cache_client: aiocache.Cache, sender_psid: str) -> None:
    try:
        await asyncio.wait_for(wait_for_user_choice(cache_client, sender_psid), 15.0)
    except asyncio.TimeoutError:
        await cache_client.clear()
        return await call_send_api(
            sender_psid, {"text": "선택할 시간이 지났습니다 다시 처음부터 시도해주세요"}
        )


async def handle_message(sender_psid: str, received_message: str) -> None:
    cache_client: aiocache.Cache = aiocache.Cache()
    neispy_client: neispy.Client = neispy.Client()
    text: str = received_message.get("text")
    session: bool = False
    response: dict = {"text": "없는 명령어에요!"}

    if text:
        if await cache_client.exists(sender_psid):
            if text.isdigit():
                school_list: list = await cache_client.get(sender_psid)
                await cache_client.clear()
                choice: dict = school_list[int(text) - 1]

                meal: str = await get_meal(
                    choice.ATPT_OFCDC_SC_CODE, choice.SD_SCHUL_CODE, neispy_client
                )

                response: dict = {"text": f"오늘의 급식이에요\n{meal}"}

            else:
                await cache_client.clear()
                response: dict = {"text": "잘못된 값을 주셨어요"}
        else:
            if text.startswith("!급식"):
                arg = text[3:].strip()
                result = await check_result(arg, neispy_client)

                if not result:
                    response = {"text": "학교가 존재하지않습니다."}

                elif isinstance(result, tuple):
                    ae, se = result
                    meal = await get_meal(ae, se, neispy_client)
                    response = {"text": f"오늘의 급식이에요\n{meal}"}

                else:
                    session = True

                    school_list = [
                        f"{index}. {school.SCHUL_NM} ({school.LCTN_SC_NM})"
                        for index, school in enumerate(result, 1)
                    ]

                    response = {"text": "\n".join(school_list)}

                    await cache_client.set(sender_psid, result)
                    await call_send_api(sender_psid, response)

    if session:
        asyncio.create_task(timeout(cache_client, sender_psid))
    else:
        return await call_send_api(sender_psid, response)


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