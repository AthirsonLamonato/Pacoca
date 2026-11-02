"""Optional Alexa channel. Amazon request validation is mandatory."""
from __future__ import annotations

import asyncio
from datetime import datetime,timezone
import json
import re
import uuid

from fastapi import HTTPException,Request


def response(text,end=False):
    text=re.sub(r"[*#`_]","",text)[:6000]
    return {"version":"1.0","response":{"outputSpeech":{"type":"PlainText","text":text},"shouldEndSession":end}}


def install_alexa(app,settings,store,conversations):
    verifier=None
    lock=asyncio.Lock()

    async def verify(headers,body):
        nonlocal verifier
        if verifier is None:
            from ask_sdk_webservice_support.verifier import RequestVerifier
            verifier=RequestVerifier()
        # Official verification validates the Amazon certificate URL, certificate chain and signature.
        await asyncio.to_thread(verifier.verify,dict(headers),body,None)

    app.state.alexa_verify=verify

    @app.post("/alexa")
    async def alexa(request: Request):
        if not settings.get("alexa_enabled") or not settings.get("alexa_skill_id") or not settings.get("alexa_user_id"):
            raise HTTPException(404,"Integração Alexa desativada.")
        body=await request.body()
        if len(body)>100000:
            raise HTTPException(413,"Requisição grande demais.")
        try:
            data=json.loads(body)
            stamp=datetime.fromisoformat(data["request"]["timestamp"].replace("Z","+00:00"))
            if stamp.tzinfo is None or abs((datetime.now(timezone.utc)-stamp).total_seconds())>150:
                raise ValueError("Expired timestamp")
            system=data.get("context",{}).get("System",{})
            application=system.get("application") or data.get("session",{}).get("application",{})
            user=system.get("user") or data.get("session",{}).get("user",{})
            if application.get("applicationId")!=settings.get("alexa_skill_id") or user.get("userId")!=settings.get("alexa_user_id"):
                raise ValueError("Unpaired skill or user")
            await asyncio.wait_for(app.state.alexa_verify(request.headers,body.decode("utf-8")),timeout=4)
        except (ValueError,KeyError,TypeError,asyncio.TimeoutError):
            raise HTTPException(403,"Requisição não autorizada.")
        except Exception:
            raise HTTPException(403,"Assinatura da requisição não validada.")
        req=data["request"]
        kind=req.get("type")
        if kind=="SessionEndedRequest":
            return {"version":"1.0","response":{}}
        if kind=="LaunchRequest":
            return response("Oi! Sou a Paçoca do seu computador. Diga: executar, seguido do seu pedido. Ou diga: como está meu pedido.")
        if kind!="IntentRequest":
            return response("Esse tipo de pedido não está disponível.")
        intent=req.get("intent",{})
        name=intent.get("name")
        if name in ("AMAZON.StopIntent","AMAZON.CancelIntent"):
            for run in list(conversations.runs.values()):
                if run.channel=="alexa" and not run.finished:
                    await conversations.cancel_run(run)
            return response("Certo. Interrompi os pedidos feitos pela Alexa.",True)
        if name=="AMAZON.HelpIntent":
            return response("Diga executar e seu pedido, como: executar consultar volume. Para conferir, diga como está meu pedido. Ações sensíveis precisam da janela da Paçoca.")
        cid=uuid.uuid5(uuid.NAMESPACE_URL,"pacoca:alexa:"+settings.get("alexa_user_id")).hex
        if name=="TaskStatusIntent":
            tasks=store.query("SELECT * FROM tasks WHERE conversation_id=? ORDER BY created DESC LIMIT 1",(cid,))
            if not tasks:
                return response("Você ainda não fez um pedido por aqui.")
            task=tasks[0]
            if task["status"] in ("running","waiting_approval"):
                return response("Seu pedido ainda está em andamento no computador. Consulte novamente em alguns instantes.")
            return response(task["output"] or "O pedido foi interrompido. Confira as atividades no computador.")
        if name!="CommandIntent":
            return response("Não entendi. Diga executar, seguido do que você quer fazer.")
        text=intent.get("slots",{}).get("query",{}).get("value","").strip()
        id=req.get("requestId","")
        if not text or len(text)>3000 or not id:
            return response("Diga executar e um pedido curto para o computador.")
        if conversations.runtime.info()["status"]!="ready":
            return response("Minha inteligência local ainda não está pronta. Confira a Paçoca no computador.")
        async with lock:
            duplicate=store.query("SELECT task_id FROM alexa_requests WHERE id=?",(id,))
            if duplicate:
                return response("Esse pedido já foi recebido. Diga como está meu pedido para consultar o resultado.")
            if not store.query("SELECT id FROM conversations WHERE id=?",(cid,)):
                from .store import now
                stamp=now()
                store.execute("INSERT INTO conversations(id,title,created,updated) VALUES(?,?,?,?)",(cid,"Conversa pela Alexa",stamp,stamp))
            task_id=await conversations.submit(cid,text,channel="alexa")
            from .store import now
            store.execute("INSERT INTO alexa_requests VALUES(?,?,?)",(id,task_id,now()))
        return response("Recebi seu pedido no computador. Diga como está meu pedido para consultar o resultado.")
