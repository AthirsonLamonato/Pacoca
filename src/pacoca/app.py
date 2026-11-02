from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .audio import Voice
from .browser import Browser
from .config import Settings
from .conversation import Conversations
from .runtime import LocalRuntime
from .store import Store, now
from .tools import ToolRegistry, index_folder
from .resources import ResourcePolicy
from .updates import UpdateManager,FEED
from .actions import DesktopActions
from .wake import WakeService

log = logging.getLogger(__name__)


class ChangeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_name: str | None = Field(default=None,max_length=80)
    voice_enabled: bool | None = None
    voice_speed: float | None = Field(default=None,ge=.7,le=1.4)
    microphone_id: str | None = Field(default=None,max_length=500)
    output_id: str | None = Field(default=None,max_length=500)
    wake_enabled: bool | None = None
    wake_sensitivity: str | None = Field(default=None,pattern='^(low|normal|high)$')
    wake_timeout: int | None = Field(default=None,ge=10,le=60)
    theme: str | None = Field(default=None,pattern="^(dark|light)$")
    backend: str | None = Field(default=None,pattern="^(auto|cpu)$")
    model_profile: str | None = Field(default=None,pattern="^(light|advanced)$")
    cpu_threads: int | None = Field(default=None,ge=1,le=4)
    idle_seconds: int | None = Field(default=None,ge=15,le=300)
    game_guard: bool | None = None
    updates_enabled: bool | None = None
    update_install_on_exit: bool | None = None
    application_paths: dict[str,str] | None = None
    spotify_device: str | None = Field(default=None,max_length=160)
    retention_days: int | None = Field(default=None,ge=1,le=3650)
    onboarding_done: bool | None = None
    browser_domains: list[str] | None = Field(default=None,max_length=30)
    start_with_windows: bool | None = None
    alexa_enabled: bool | None = None
    alexa_skill_id: str | None = Field(default=None,max_length=200)
    alexa_user_id: str | None = Field(default=None,max_length=300)


class ChatRequest(BaseModel):
    conversation_id: str
    text: str = Field(min_length=1,max_length=6000)
    voice: bool = False


class Text(BaseModel):
    content: str = Field(min_length=1,max_length=2000)


class Folder(BaseModel):
    path: str = Field(min_length=1,max_length=2000)


def create_app(settings=None, runtime=None, *, start_engine=True, update_feed=None):
    settings = settings or Settings()
    store = Store(settings.directory / "pacoca.sqlite3")
    runtime = runtime or LocalRuntime(settings)
    browser = Browser(settings)
    voice = Voice(runtime,settings)
    wake = WakeService(settings)
    actions=DesktopActions(settings,runtime)
    tools = ToolRegistry(settings,store,browser,actions)
    conversations = Conversations(settings,store,runtime,tools,voice)
    token = secrets.token_urlsafe(32)
    index_state = {"running":False,"message":""}
    background = set()
    ui_sessions={}

    def update_blocker():
        if wake.active_until > time.monotonic():return 'Aguardando a conversa por voz começar'
        if any(not r.finished for r in conversations.runs.values()):return 'Aguardando o pedido atual terminar'
        if conversations.approvals:return 'Aguardando sua decisão sobre uma ação'
        if index_state['running']:return 'Aguardando a atualização dos documentos'
        if any(s.get('voice') or s.get('playback') for s in ui_sessions.values()):return 'Aguardando a conversa por voz terminar'
        if any(s.get('draft') for s in ui_sessions.values()):return 'Aguardando você terminar de escrever'
        return ''

    updates=UpdateManager(settings,getattr(runtime,'policy',ResourcePolicy(settings)),conversations.emit,
                          update_blocker,feed=update_feed or FEED)
    updates.backup=store.backup

    def spawn(coro):
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)
        return task

    async def reminders_loop():
        while True:
            for reminder in store.query("SELECT * FROM reminders WHERE done=0"):
                try:
                    if datetime.fromisoformat(reminder["due"]) <= datetime.now().astimezone():
                        store.execute("UPDATE reminders SET done=1 WHERE id=?",(reminder["id"],))
                        await conversations.emit("reminder",text=reminder["text"],id=reminder["id"])
                except ValueError:
                    log.warning("Invalid reminder timestamp")
            await asyncio.sleep(10)

    async def idle_audio():
        while True:
            await asyncio.sleep(5)
            await asyncio.to_thread(voice.release_idle)

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        store.cleanup(settings.get("retention_days"))
        if start_engine:
            await runtime.start()
        spawn(idle_audio())
        spawn(updates.loop())
        spawn(reminders_loop())
        yield
        await conversations.stop()
        tasks = [r.task for r in conversations.runs.values() if r.task and not r.task.done()]
        for task in list(background):
            task.cancel()
        await asyncio.gather(*tasks,*background,return_exceptions=True)
        await browser.close()
        voice.close()
        wake.close()
        actions.close()
        await runtime.close()
        if settings.get('update_install_on_exit',True) and updates.state['phase']=='ready':
            try:await updates.apply(exiting=True)
            except Exception:log.exception('Update on exit could not start')
        await updates.close()
        store.close()

    app = FastAPI(title="Paçoca",version=__version__,docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.token,app.state.settings,app.state.runtime = token,settings,runtime
    app.state.store,app.state.conversations,app.state.tools = store,conversations,tools
    app.state.updates=updates
    app.state.wake=wake
    updates.shutdown=lambda:getattr(app.state,'shutdown',lambda:None)()
    from .alexa import install_alexa
    install_alexa(app,settings,store,conversations)

    def allowed_origin(origin, host):
        if not origin:
            return True
        parsed = urlparse(origin)
        return parsed.scheme == "http" and parsed.netloc == host

    @app.middleware("http")
    async def protect(request: Request, call_next):
        host = request.headers.get("host","")
        if host.split(":")[0] not in ("127.0.0.1","localhost","testserver"):
            return JSONResponse({"detail":"Host inválido"},status_code=403)
        if not allowed_origin(request.headers.get("origin"),host):
            return JSONResponse({"detail":"Origem inválida"},status_code=403)
        if request.url.path.startswith("/api/") and not secrets.compare_digest(request.headers.get("X-Pacoca-Token",""),token):
            return JSONResponse({"detail":"Abra a Paçoca pelo aplicativo para acessar seus dados."},status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' qrc:; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' ws://127.0.0.1:*; media-src 'self' blob: data:; object-src 'none'; frame-ancestors 'none'"
        return response

    @app.get("/api/status")
    async def status():
        import psutil
        return {"version":__version__,"engine":runtime.info(),"voice":voice.info(),"wake":wake.info(),"settings":settings.all(),
                "stats":{"conversations":store.query("SELECT count(*) n FROM conversations")[0]["n"],
                         "memories":store.query("SELECT count(*) n FROM memories")[0]["n"],
                         "documents":store.query("SELECT count(*) n FROM documents")[0]["n"]},
                "hardware":{"ram_gb":round(psutil.virtual_memory().total/1024**3),"cpu_percent":psutil.cpu_percent()},
                "index":index_state,"workspace":str(settings.workspace),'update':updates.info()}

    @app.get('/api/updates')
    async def update_status():return updates.info()

    @app.get('/api/applications')
    async def applications():return await asyncio.to_thread(actions.catalog.entries,True)

    @app.get('/api/actions/capabilities')
    async def action_capabilities():
        from .screen import recognize
        from PIL import Image,ImageDraw,ImageFont
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        image=Image.new('RGB',(620,120),'white')
        draw=ImageDraw.Draw(image)
        font=ImageFont.truetype(str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'Fonts/arial.ttf'),40)
        draw.text((20,20),'PACOCA JOGAR MATA-MATA',font=font,fill='black')
        lines=await recognize(image)
        manager=await GlobalSystemMediaTransportControlsSessionManager.request_async()
        return {'ocr':any('JOGAR' in x['text'] for x in lines),'media':True,
                'spotify_session':any('spotify' in s.source_app_user_model_id.casefold() for s in manager.get_sessions()),
                'actions':['open','deathmatch','play','pause','resume','next','previous','transfer','devices']}

    @app.post('/api/updates/check')
    async def check_update():return await updates.check()

    @app.post('/api/updates/download')
    async def download_update():
        if not updates.package:raise HTTPException(409,'Verifique a atualização primeiro')
        spawn(updates.download())
        return updates.info()

    @app.post('/api/updates/apply')
    async def apply_update():return await updates.apply()

    @app.get("/api/settings")
    async def get_settings():
        return settings.all()

    @app.patch("/api/settings")
    async def update_settings(changes: ChangeSettings):
        data = changes.model_dump(exclude_none=True)
        if 'application_paths' in data:
            if any(key not in ('cs2','valorant','spotify') for key in data['application_paths']):raise HTTPException(422,'Escolha CS2, Valorant ou Spotify.')
            for value in data['application_paths'].values():
                if value and (not Path(value).is_absolute() or not Path(value).is_file() or Path(value).suffix.casefold()!='.exe'):
                    raise HTTPException(422,'Escolha um executável .exe instalado neste computador.')
        if "browser_domains" in data:
            import re
            if any(not re.fullmatch(r"[a-zA-Z0-9.-]{1,250}",d) for d in data["browser_domains"]):
                raise HTTPException(422,"Informe somente os nomes dos domínios.")
        if "start_with_windows" in data:
            if os.name != "nt":
                raise HTTPException(400,"Inicialização automática disponível somente no Windows.")
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                if data["start_with_windows"]:
                    if not getattr(sys,"frozen",False):
                        raise HTTPException(400,"A inicialização automática fica disponível na versão instalada.")
                    winreg.SetValueEx(key,"Pacoca",0,winreg.REG_SZ,'"'+sys.executable+'" --minimized')
                else:
                    try:
                        winreg.DeleteValue(key,"Pacoca")
                    except FileNotFoundError:
                        pass
        previous=settings.all()
        updated=settings.update(data)
        if any(key in data and data[key]!=previous.get(key) for key in ('wake_enabled','wake_sensitivity')):
            await asyncio.to_thread(wake.close)
        if any(key in data and data[key]!=previous.get(key) for key in ('model_profile','backend','cpu_threads')):
            await conversations.stop()
            await runtime.stop_process()
        return updated

    @app.get("/api/conversations")
    async def list_conversations():
        return store.conversations()

    @app.post("/api/conversations")
    async def create_conversation():
        return store.conversation()

    @app.get("/api/conversations/{id}")
    async def get_conversation(id: str):
        rows = store.query("SELECT * FROM conversations WHERE id=?",(id,))
        if not rows:
            raise HTTPException(404,"Conversa não encontrada.")
        return {**rows[0],"messages":store.messages(id,200)}

    @app.delete("/api/conversations/{id}")
    async def delete_conversation(id: str):
        await conversations.cancel_conversation(id)
        tasks = [r.task for r in conversations.runs.values() if r.conversation_id==id and r.task]
        await asyncio.gather(*tasks,return_exceptions=True)
        store.execute("DELETE FROM conversations WHERE id=?",(id,))
        return {"ok":True}

    @app.post("/api/chat")
    async def chat(request: ChatRequest):
        try:
            id = await conversations.submit(request.conversation_id,request.text.strip(),request.voice)
        except ValueError as exc:
            raise HTTPException(404,str(exc))
        return {"run_id":id}

    @app.post("/api/stop")
    async def stop():
        settings.update({'wake_enabled':False})
        await asyncio.to_thread(wake.close)
        await conversations.stop()
        voice.close()
        await runtime.stop_process()
        return {"ok":True}

    @app.post("/api/activate")
    async def activate():
        callback=getattr(app.state,'activate',None)
        if callback:
            callback()
        return {"ok":True}

    @app.post("/api/shutdown")
    async def shutdown():
        callback=getattr(app.state,'shutdown',None)
        if callback:
            callback()
        return {"ok":True}

    @app.post("/api/approvals/{id}")
    async def approve(id: str, request: Request):
        data = await request.json()
        if not isinstance(data.get("allowed"),bool):
            raise HTTPException(422,"Decisão inválida.")
        try:
            await conversations.approve(id,data["allowed"])
        except ValueError as exc:
            raise HTTPException(409,str(exc))
        return {"ok":True}

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        body = await request.body()
        if len(body) > 16000*45*4 or len(body)%4:
            raise HTTPException(413,"Envie áudio PCM float32 de até 45 segundos.")
        try:
            text = await asyncio.to_thread(voice.transcribe,body)
            return {"text":text}
        except (ValueError,RuntimeError,FileNotFoundError) as exc:
            raise HTTPException(400,str(exc))

    @app.post("/api/voice/preview")
    async def preview_voice():
        try:
            wav = await asyncio.to_thread(voice.synthesize,"Oi! Eu sou a Paçoca. Sua inteligência pessoal, aqui no seu computador.")
            return Response(wav,media_type="audio/wav")
        except Exception as exc:
            raise HTTPException(503,"Não consegui carregar a voz local: " + str(exc)[:180])

    @app.get("/api/memories")
    async def memories():
        return store.memories()

    @app.post("/api/memories")
    async def remember(text: Text):
        return {"id":store.remember(text.content)}

    @app.patch("/api/memories/{id}")
    async def edit_memory(id: str,text: Text):
        store.execute("UPDATE memories SET content=?,updated=? WHERE id=?",(text.content,now(),id))
        return {"ok":True}

    @app.delete("/api/memories/{id}")
    async def forget(id: str):
        store.execute("DELETE FROM memories WHERE id=?",(id,))
        return {"ok":True}

    @app.get("/api/knowledge")
    async def knowledge():
        return {"roots":[str(r) for r in settings.roots()],"documents":store.query("SELECT id,path,title FROM documents ORDER BY title LIMIT 300"),"index":index_state}

    @app.post("/api/knowledge/roots")
    async def add_root(folder: Folder):
        path = Path(folder.path).expanduser().resolve()
        if not path.is_dir():
            raise HTTPException(400,"Essa pasta não existe.")
        roots = list(dict.fromkeys([*settings.get("allowed_roots",[]),str(path)]))
        settings.update({"allowed_roots":roots})
        return {"roots":roots}

    @app.delete("/api/knowledge/roots")
    async def remove_root(folder: Folder):
        path = Path(folder.path).resolve()
        roots = [r for r in settings.get("allowed_roots",[]) if Path(r).resolve()!=path]
        settings.update({"allowed_roots":roots})
        for doc in store.query("SELECT id,path FROM documents"):
            if not tools._authorized(doc["path"]):
                store.execute("DELETE FROM document_search WHERE document_id=?",(doc["id"],))
                store.execute("DELETE FROM documents WHERE id=?",(doc["id"],))
        return {"ok":True}

    @app.post("/api/knowledge/index")
    async def index():
        if index_state["running"]:
            raise HTTPException(409,"A indexação já está em andamento.")
        index_state.update(running=True,message="Lendo as pastas autorizadas")
        async def work():
            indexed, skipped = 0, 0
            try:
                for root in settings.roots():
                    result = await asyncio.to_thread(index_folder,settings,store,str(root))
                    indexed += result["indexed"]
                    skipped += result["skipped"]
                index_state["message"] = f"{indexed} documentos disponíveis · {skipped} ignorados"
            except Exception as exc:
                index_state["message"] = str(exc)[:200]
            finally:
                index_state["running"] = False
                await conversations.emit("knowledge_updated",**index_state)
        spawn(work())
        return index_state

    @app.get("/api/knowledge/search")
    async def search(q: str):
        return [d for d in store.search(q[:1000]) if tools._authorized(d["path"])]

    @app.get("/api/tasks")
    async def tasks():
        return store.query("SELECT * FROM tasks ORDER BY created DESC LIMIT 100")

    @app.get("/api/tasks/{id}")
    async def task(id: str):
        rows = store.query("SELECT * FROM tasks WHERE id=?",(id,))
        if not rows:
            raise HTTPException(404,"Tarefa não encontrada.")
        events = store.query("SELECT * FROM events WHERE task_id=? ORDER BY id",(id,))
        return {**rows[0],"events":[{**e,"data":json.loads(e["data"])} for e in events]}

    @app.get("/api/reminders")
    async def reminders():
        return store.query("SELECT * FROM reminders ORDER BY due DESC LIMIT 50")

    @app.delete("/api/reminders/{id}")
    async def delete_reminder(id: str):
        store.execute("DELETE FROM reminders WHERE id=?",(id,))
        return {"ok":True}

    @app.post("/api/runtime/restart")
    async def restart():
        await conversations.stop()
        await runtime.stop_process()
        voice.close()
        await runtime.start()
        return {"ok":True}

    @app.get("/api/diagnostics")
    async def diagnostics():
        path = settings.directory / "engine.log"
        tail = path.read_text(encoding="utf-8",errors="replace")[-8000:] if path.exists() else ""
        tail = tail.replace(runtime.key,"[oculto]")
        return {"engine":runtime.info(),"data_directory":str(settings.directory),"assets_directory":str(runtime.assets),"log":tail}

    @app.get("/api/export")
    async def export():
        result = {"version":__version__,"exported":now(),"conversations":store.conversations(),
                  "messages":store.query("SELECT * FROM messages ORDER BY created"),"memories":store.memories(),"settings":settings.all()}
        return Response(json.dumps(result,ensure_ascii=False,indent=2),media_type="application/json",
                        headers={"Content-Disposition":"attachment; filename=pacoca-backup.json"})

    @app.websocket('/wake')
    async def wake_audio(ws: WebSocket):
        host = ws.headers.get('host','')
        if host.split(':')[0] not in ('127.0.0.1','localhost','testserver') or not allowed_origin(ws.headers.get('origin'),host) or not secrets.compare_digest(ws.query_params.get('token',''),token):
            await ws.close(code=1008); return
        await ws.accept()
        owner=secrets.token_hex(16)
        try:
            await ws.send_json(await asyncio.to_thread(wake.open,owner))
            while True:
                # Silence still sends PCM; missing frames mean the client went away.
                message=await asyncio.wait_for(ws.receive(),10)
                if message['type']=='websocket.disconnect':break
                if 'bytes' in message and message['bytes'] is not None:
                    data=message['bytes']
                elif message.get('text')=='reset':data='reset'
                elif message.get('text')=='ping':
                    await ws.send_json({'type':'pong'});continue
                else:raise ValueError('Mensagem de escuta inválida.')
                await ws.send_json(await asyncio.to_thread(wake.feed,owner,data))
        except (WebSocketDisconnect, RuntimeError, ValueError, TimeoutError, EOFError, OSError) as exc:
            try:await ws.send_json({'type':'error','message':str(exc)[:160]})
            except (RuntimeError, OSError):pass
        finally:
            await asyncio.to_thread(wake.close,owner)
            try:await ws.close()
            except RuntimeError:pass

    @app.websocket("/events")
    async def events(ws: WebSocket):
        host = ws.headers.get("host","")
        if host.split(":")[0] not in ("127.0.0.1","localhost","testserver") or not allowed_origin(ws.headers.get("origin"),host) or not secrets.compare_digest(ws.query_params.get("token",""),token):
            await ws.close(code=1008)
            return
        await ws.accept()
        queue = asyncio.Queue(maxsize=2000)
        session_id=secrets.token_hex(8)
        ui_sessions[session_id]={}
        conversations.listeners.add(queue)
        async def send():
            while True:
                await ws.send_json(await queue.get())
        sender = asyncio.create_task(send())
        try:
            await ws.send_json({"type":"connected"})
            while True:
                message = await ws.receive_json()
                if message.get("type") == "interrupt":
                    run = conversations.runs.get(message.get("run_id"))
                    if run and run.conversation_id == message.get("conversation_id"):
                        await conversations.cancel_run(run)
                elif message.get("type") == "played":
                    run = conversations.runs.get(message.get("run_id"))
                    if run and not run.cancel.is_set():
                        run.heard.append(str(message.get("text",""))[:3000])
                elif message.get('type')=='activity':
                    ui_sessions[session_id]={key:message.get(key) is True for key in ('voice','playback','draft')}
        except (WebSocketDisconnect,ValueError):
            pass
        finally:
            sender.cancel()
            conversations.listeners.discard(queue)
            ui_sessions.pop(session_id,None)

    ui = Path(__file__).parent / "ui"
    app.mount("/static",StaticFiles(directory=ui),name="static")

    @app.get("/")
    async def home():
        return FileResponse(ui / "index.html")

    return app
