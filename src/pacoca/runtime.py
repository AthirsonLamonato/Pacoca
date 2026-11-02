from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

import httpx

from .config import asset_root
from .resources import ResourcePolicy

log = logging.getLogger(__name__)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalRuntime:
    def __init__(self, settings):
        self.settings = settings
        self.assets = asset_root()
        self.status = "sleeping"
        self.detail = "Modo leve · carrego a inteligência quando você precisar"
        self.backend = ""
        self.process = None
        self.log_file = None
        self.port = free_port()
        self.key = secrets.token_urlsafe(32)
        self.url = f"http://127.0.0.1:{self.port}"
        self.lock = asyncio.Lock()
        self.inference = asyncio.Semaphore(1)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(180, connect=5), trust_env=False)
        self.manifest = {}
        self.policy=ResourcePolicy(settings)
        self.last_used=time.monotonic()
        self.active=self.inflight=0
        self.loaded_profile=None
        self.signature=None
        self.guard_task=None
        from .processes import ProcessJob
        self.job=ProcessJob()

    def resource(self, key):
        relative = self.manifest.get(key)
        if not relative:
            raise FileNotFoundError(f"Recurso local ausente: {key}")
        path = (self.assets / relative).resolve()
        if not path.is_relative_to(self.assets.resolve()) or not path.exists():
            raise FileNotFoundError(f"Recurso local ausente: {key}")
        return path

    async def start(self):
        self.read_manifest()
        if not self.guard_task:
            self.guard_task=asyncio.create_task(self.guard())

    def read_manifest(self):
        self.manifest=json.loads((self.assets/'manifest.json').read_text(encoding='utf-8'))

    def model_spec(self,profile=None):
        if not self.manifest:
            self.read_manifest()
        profile=profile or self.policy.profile()
        models=self.manifest.get('models',{})
        if models:
            return models[profile]
        # Never accidentally use the old 8B as the supposedly lightweight model.
        if profile=='light':
            return {'path':'models/chat-light.gguf','name':'Qwen3 1.7B · Leve'}
        return {'path':self.manifest['model'],'name':self.manifest['name']}

    @asynccontextmanager
    async def session(self):
        self.active+=1
        try:
            yield
        finally:
            self.active-=1
            self.last_used=time.monotonic()

    @asynccontextmanager
    async def request(self):
        self.inflight+=1
        try:
            await self.ensure_ready()
            async with self.inference:
                yield
        finally:
            self.inflight-=1
            self.last_used=time.monotonic()

    async def guard(self):
        try:
            while True:
                await asyncio.sleep(2)
                if self.process and self.process.poll() is None:
                    game=self.settings.get('game_guard',True) and self.policy.games()
                    if (game and self.loaded_profile=='advanced') or (
                        not self.active and not self.inflight and
                        time.monotonic()-self.last_used>=self.settings.get('idle_seconds',60)):
                        await self.stop_process()
        except asyncio.CancelledError:
            pass

    async def ensure_ready(self):
        async with self.lock:
            try:
                self.read_manifest()
                profile=self.policy.profile()
                threads=max(1,min(4,int(self.settings.get('cpu_threads',2))))
                context=max(2048,min(8192 if profile=='advanced' else 4096,int(self.settings.get('context_size',4096))))
                signature=(profile,threads,context,self.settings.get('backend','auto'))
                if self.process and self.process.poll() is None and self.signature==signature:
                    return
                await self._stop_process()
                spec=self.model_spec(profile)
                model=(self.assets/spec['path']).resolve()
                if not model.is_relative_to(self.assets.resolve()) or not model.is_file():
                    raise FileNotFoundError('O modelo '+spec['name']+' não está instalado. Use o instalador atualizado ou selecione o modo leve.')
                import psutil
                if psutil.virtual_memory().available < (8 if profile=='advanced' else 4)*1024**3:
                    raise RuntimeError('Pouca memória livre para carregar esse modelo. Feche um programa ou use o modo leve.')
                engine=self.resource('engine')
                backends = [("cpu",engine)]
                if profile=='advanced' and self.settings.get("backend") != "cpu":
                    backends.insert(0,("vulkan",engine))
                    if os.name=='nt' and self.manifest.get('engine_cuda'):
                        try:
                            import ctypes
                            if ctypes.WinDLL('nvcuda.dll').cuInit(0)==0:
                                backends.insert(0,("cuda",self.resource('engine_cuda')))
                        except (OSError,FileNotFoundError):
                            pass
                self.status = "loading"
                for backend,engine in backends:
                    self.detail = "Carregando o modelo na " + ("CPU" if backend == "cpu" else "placa de vídeo")
                    self.log_file = (self.settings.directory / "engine.log").open("a", encoding="utf-8")
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    args = [str(engine), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
                            "--api-key", self.key, "-c", str(context), "-np", "1",
                            "-ngl", "0" if backend == "cpu" else "99", "-t", str(threads),
                            '-tb',str(threads),'--poll','0','--poll-batch','0','--prio','-1',
                            '-b','128','-ub','64',"--jinja", "--reasoning", "off", "--no-webui"]
                    if backend=='cpu':
                        args+=['--device','none']
                    env={**os.environ,'OMP_NUM_THREADS':str(threads),'OPENBLAS_NUM_THREADS':'1'}
                    self.process = subprocess.Popen(args, cwd=engine.parent, stdout=self.log_file,
                                                    stderr=subprocess.STDOUT, creationflags=flags,env=env)
                    self.job.cpu_limit(15 if profile=='light' else 30)
                    self.job.attach(self.process)
                    for _ in range(240):
                        if self.process.poll() is not None:
                            break
                        try:
                            result = await self.client.get(self.url + "/health", headers=self.headers)
                            if result.status_code == 200:
                                self.status, self.backend, self.detail = "ready", backend, "Pronta para conversar"
                                self.loaded_profile=profile;self.signature=signature;self.last_used=time.monotonic()
                                return
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(.5)
                    await self._stop_process()
                raise RuntimeError("O modelo não iniciou. Consulte o diagnóstico para tentar novamente.")
            except Exception as exc:
                log.exception("Local runtime startup failed")
                self.status, self.detail = "error", str(exc)
                raise

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.key}"}

    def info(self):
        if self.status == "ready" and self.process and self.process.poll() is not None:
            self.status, self.detail = "error", "O motor local foi interrompido. Reinicie-o em Configurações."
        try:
            spec=self.model_spec(self.loaded_profile or self.policy.profile())
            advanced=(self.assets/self.model_spec('advanced')['path']).is_file()
        except (OSError,ValueError,KeyError):
            spec={'name':'Modelo local'};advanced=False
        return dict(status=self.status, detail=self.detail, backend=self.backend,
                    model=spec['name'],profile=self.loaded_profile or self.policy.profile(),
                    loaded=bool(self.process and self.process.poll() is None),
                    pid=self.process.pid if self.process and self.process.poll() is None else None,
                    advanced_available=advanced,policy=self.policy.info())

    async def select_tool(self,messages,schemas):
        """A bounded local semantic decision; actions cannot become unverified prose."""
        names=[t['function']['name'] for t in schemas if t['function']['name']!='respond_to_user']
        catalog='\n'.join(t['function']['name']+': '+t['function']['description'] for t in schemas if t['function']['name']!='respond_to_user')
        context=json.dumps(messages[-6:],ensure_ascii=False)[-11000:]
        last_user=max((i for i,m in enumerate(messages) if m.get('role')=='user'),default=0)
        request=messages[last_user].get('content','')
        observed=[m for m in messages[last_user+1:] if m.get('role')=='tool']
        prompt=('Escolha a próxima etapa para atender a última mensagem do usuário. Retorne apenas JSON.\n'
                'Escolha conversation SOMENTE se for conversa geral, uma pergunta sem necessidade de ferramenta, '
                'ou se os resultados de ferramentas JÁ consultados neste pedido forem suficientes para responder.\n'
                'Consultar estado do computador, arquivos, janelas, volume, hora, memórias ou lembretes SEMPRE '
                'exige a ferramenta correspondente antes da resposta. Não use exemplos ou suposições como resultados reais.\n'
                'Pedidos explícitos de criar, guardar ou alterar exigem a ferramenta de ação. '
                'Se o usuário disser para NÃO guardar, não use remember. Não refaça uma ação já executada neste pedido. '
                'Uma aprovação negada encerra essa ação: conversation para explicar. Consultar não é modificar: '
                '"não altere" e "não interaja" permitem ferramentas de leitura para responder à consulta solicitada.\n'
                'Exemplos: "oi" => conversation; "volume atual" => volume; "janelas abertas" => list_windows; '
                '"guarde esta preferência" => remember; "lembre-me amanhã" => create_reminder; '
                '"leia arquivo" => files; "consulte as memórias salvas" => list_memories.\n'+catalog)
        schema={'type':'object','properties':{'tool':{'type':'string','enum':['conversation',*names]}},'required':['tool'],'additionalProperties':False}
        async with self.request():
            result=await self.client.post(self.url+'/v1/chat/completions',headers=self.headers,json={
                'model':'local','messages':[{'role':'system','content':prompt},{'role':'user','content':
                    'Pedido ATUAL: '+str(request)+'\nResultados de ferramentas executadas NESTE pedido: '+json.dumps(observed,ensure_ascii=False)[-5000:]+
                    '\nHistórico para referências apenas; não comprova estado atual: '+context}],
                'temperature':0,'max_tokens':48,'stream':False,'chat_template_kwargs':{'enable_thinking':False},
                'response_format':{'type':'json_schema','json_schema':{'name':'next_step','strict':True,'schema':schema}}})
            result.raise_for_status()
            raw=result.json()['choices'][0]['message']['content']
            selected=json.loads(raw)['tool']
            if selected not in ['conversation',*names]:
                raise ValueError('Decisão local inválida. Nenhuma ação foi executada.')
            return selected

    async def arguments_for(self,tool,messages):
        schema=tool['function']['parameters']
        if not schema.get('properties'):
            return {}
        instruction=('Prepare SOMENTE os argumentos JSON para a ferramenta '+tool['function']['name']+'. '
                     'Não execute nada e não descreva resultados. Respeite os caminhos autorizados do sistema. '
                     'Para salvar no Workspace use somente o nome do arquivo. '
                     'Uma consulta de volume sem alteração usa level null. '
                     'A mensagem mais recente do usuário é o pedido atual; os demais turnos são contexto.\n'+tool['function']['description'])
        async with self.request():
            result=await self.client.post(self.url+'/v1/chat/completions',headers=self.headers,json={
                'model':'local','messages':[messages[0],{'role':'system','content':instruction},*messages[1:]],
                'temperature':0,'max_tokens':2048,'stream':False,'chat_template_kwargs':{'enable_thinking':False},
                'response_format':{'type':'json_schema','json_schema':{'name':'tool_arguments','strict':True,'schema':schema}}})
            result.raise_for_status()
            return json.loads(result.json()['choices'][0]['message']['content'])

    async def stream(self, messages, tools=None, *, require_tool=False,tool_choice=None):
        # First actions use grammar-constrained arguments. Native tool choice alone can
        # still produce an ungrounded text response in some small local models.
        if tools and isinstance(tool_choice,dict):
            name=tool_choice['function']['name']
            tool=next(t for t in tools if t['function']['name']==name)
            args=await self.arguments_for(tool,messages)
            yield {'delta':{'tool_calls':[{'index':0,'id':secrets.token_hex(12),'type':'function',
                    'function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]},'finish_reason':'tool_calls'}
            return
        async with self.request():
            payload = dict(model="local", messages=messages, stream=True, temperature=.55,
                           max_tokens=768 if self.loaded_profile=='advanced' else 384,
                           chat_template_kwargs={"enable_thinking": False})
            if tools:
                payload.update(tools=tools, tool_choice=tool_choice or ("required" if require_tool else "auto"), parallel_tool_calls=False)
            async with self.client.stream("POST", self.url + "/v1/chat/completions", headers=self.headers, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line[6:] == "[DONE]":
                        break
                    data = json.loads(line[6:])
                    if data.get("choices"):
                        yield data["choices"][0]

    async def complete(self, messages, max_chars=4000):
        text = ""
        async for choice in self.stream(messages):
            text += choice.get("delta", {}).get("content") or ""
            if len(text) > max_chars:
                break
        return text

    async def stop_process(self):
        async with self.lock:
            await self._stop_process()
            self.status='sleeping';self.loaded_profile=None;self.backend=''
            self.detail='Modo leve · inteligência liberada até o próximo pedido'

    async def _stop_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait)
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    async def close(self):
        if self.guard_task:
            self.guard_task.cancel()
            await asyncio.gather(self.guard_task,return_exceptions=True)
        await self.stop_process()
        self.job.close()
        await self.client.aclose()
