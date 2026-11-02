import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pacoca.app import create_app
from pacoca.config import Settings
from pacoca.store import Store
from pacoca.browser import Browser
from pacoca.tools import ToolRegistry,index_folder
from pacoca.conversation import Conversations


class FakeRuntime:
    def __init__(self, rounds=None):
        self.status="ready"
        self.detail="Pronta"
        self.key="fake-engine-key"
        self.assets=Path(".")
        self.rounds=list(rounds or [[{"delta":{"content":"Olá. Estou no seu computador."},"finish_reason":"stop"}]])
        self.inputs=[]

    def info(self):
        return {"status":self.status,"model":"Test","detail":self.detail,"backend":"cpu"}

    async def stream(self,messages,tools=None,**kwargs):
        self.inputs.append(messages.copy())
        for item in self.rounds.pop(0):
            await asyncio.sleep(0)
            yield item

    async def select_tool(self,messages,schemas):
        choice=self.rounds[0][0]
        calls=choice.get('delta',{}).get('tool_calls',[])
        return calls[0]['function']['name'] if calls else 'conversation'

    async def close(self):
        pass

    async def stop_process(self):
        self.status='sleeping'

    @asynccontextmanager
    async def session(self):
        yield


@pytest.fixture
def service(tmp_path):
    settings=Settings(tmp_path)
    store=Store(tmp_path/"test.db")
    registry=ToolRegistry(settings,store,Browser(settings))
    yield settings,store,registry
    store.close()


def test_preferences_persist_without_changing_application_files(tmp_path):
    s=Settings(tmp_path)
    s.update({"user_name":"Athy","backend":"cpu","unknown_key":"ignored"})
    assert Settings(tmp_path).get("user_name")=="Athy"
    assert "unknown_key" not in Settings(tmp_path).all()


def test_paths_cannot_escape_authorized_roots(tmp_path):
    s=Settings(tmp_path/"app")
    with pytest.raises(PermissionError):
        s.resolve_path(str(tmp_path/"outside.txt"),must_exist=False)
    with pytest.raises(PermissionError):
        s.resolve_path("../../outside.txt",must_exist=False)


def test_memory_survives_restart_and_can_be_forgotten(tmp_path):
    path=tmp_path/"db.sqlite"
    db=Store(path)
    id=db.remember("Prefiro respostas diretas.")
    db.close()
    db=Store(path)
    assert db.memories()[0]["content"]=="Prefiro respostas diretas."
    db.execute("DELETE FROM memories WHERE id=?",(id,))
    assert db.memories()==[]
    db.close()


def test_index_search_has_source_and_excludes_credentials(service):
    settings,store,_=service
    (settings.workspace/"projeto.md").write_text("A obra tem prazo em dezembro e orçamento aprovado.",encoding="utf-8")
    (settings.workspace/"credentials.json").write_text('{"secret":"never-index"}',encoding="utf-8")
    result=index_folder(settings,store,str(settings.workspace))
    assert result["indexed"]==1
    found=store.search("orçamento da obra")
    assert len(found)==1
    assert found[0]["path"].endswith("projeto.md")
    assert not store.search("never-index")


def test_removed_document_disappears_from_search(service):
    settings,store,_=service
    path=settings.workspace/"note.txt"
    path.write_text("Orçamento da obra",encoding="utf-8")
    index_folder(settings,store,str(settings.workspace))
    path.unlink()
    index_folder(settings,store,str(settings.workspace))
    assert store.search("orçamento")==[]


def test_schema_is_generated_from_executor_contract(service):
    _,_,tools=service
    definitions={d["function"]["name"]:d["function"]["parameters"] for d in tools.schemas()}
    assert definitions["volume"]["additionalProperties"] is False
    with pytest.raises(ValueError):
        tools.validate("volume",{"level":101})
    with pytest.raises(ValueError):
        tools.validate("volume",{"level":20,"shell":"anything"})
    with pytest.raises(ValueError):
        tools.validate("not_a_tool",{})


@pytest.mark.asyncio
async def test_file_write_is_verified_and_outside_path_is_rejected(service):
    settings,_,tools=service
    assert tools.requires_approval("write_file",tools.validate("write_file",{"path":"note.txt","content":"Oi"}))
    result=await tools.execute("write_file",tools.validate("write_file",{"path":"note.txt","content":"Oi"}))
    assert result["data"]["verified"] is True
    assert (settings.workspace/"note.txt").read_text()=="Oi"
    result=await tools.execute("write_file",tools.validate("write_file",{"path":"../../x.txt","content":"Oi"}))
    assert result["ok"] is False


def tool_round(name,args):
    return [{"delta":{"tool_calls":[{"index":0,"id":"call-1","function":{"name":name,"arguments":json.dumps(args)}}]},"finish_reason":"tool_calls"}]


@pytest.mark.asyncio
async def test_agent_feeds_observed_result_back_to_model(service):
    settings,store,tools=service
    runtime=FakeRuntime([tool_round("current_time",{}),[{"delta":{"content":"Consultei a hora real."},"finish_reason":"stop"}]])
    conversations=Conversations(settings,store,runtime,tools,None)
    cid=store.conversation()["id"]
    id=await conversations.submit(cid,"Que horas são?")
    await conversations.runs[id].task
    assert len(runtime.inputs)==2
    assert runtime.inputs[1][-1]["role"]=="tool"
    assert json.loads(runtime.inputs[1][-1]["content"])["ok"]
    assert store.query("SELECT status FROM tasks WHERE id=?",(id,))[0]["status"]=="completed"


@pytest.mark.asyncio
async def test_denied_approval_does_not_execute_tool(service):
    settings,store,tools=service
    runtime=FakeRuntime([tool_round("write_file",{"path":"never.txt","content":"No"}),[{"delta":{"content":"Ação não executada."},"finish_reason":"stop"}]])
    service=Conversations(settings,store,runtime,tools,None)
    queue=asyncio.Queue();service.listeners.add(queue)
    id=await service.submit(store.conversation()["id"],"Salve o arquivo")
    while True:
        event=await asyncio.wait_for(queue.get(),3)
        if event["type"]=="approval":
            await service.approve(event["id"],False)
            break
    await service.runs[id].task
    assert not (settings.workspace/"never.txt").exists()
    assert json.loads(runtime.inputs[1][-1]["content"])["ok"] is False


@pytest.mark.asyncio
async def test_cancelled_approval_cannot_execute_later(service):
    settings,store,tools=service
    runtime=FakeRuntime([tool_round("write_file",{"path":"never.txt","content":"No"})])
    service=Conversations(settings,store,runtime,tools,None)
    queue=asyncio.Queue();service.listeners.add(queue)
    id=await service.submit(store.conversation()["id"],"Salve")
    while (event:=await asyncio.wait_for(queue.get(),3))["type"]!="approval":
        pass
    await service.cancel_run(service.runs[id])
    await asyncio.gather(service.runs[id].task,return_exceptions=True)
    with pytest.raises(ValueError):
        await service.approve(event["id"],True)
    assert not (settings.workspace/"never.txt").exists()
    assert store.query("SELECT status FROM tasks WHERE id=?",(id,))[0]["status"]=="cancelled"


@pytest.mark.asyncio
async def test_alexa_cannot_request_desktop_write(service):
    settings,store,tools=service
    runtime=FakeRuntime([tool_round("write_file",{"path":"never.txt","content":"No"}),[{"delta":{"content":"Autorize no computador."},"finish_reason":"stop"}]])
    service=Conversations(settings,store,runtime,tools,None)
    id=await service.submit(store.conversation()["id"],"Salve",channel="alexa")
    await service.runs[id].task
    assert not service.approvals
    assert not (settings.workspace/"never.txt").exists()


def test_api_rejects_unauthenticated_and_foreign_origins(tmp_path):
    app=create_app(Settings(tmp_path),FakeRuntime(),start_engine=False)
    with TestClient(app) as c:
        assert c.get('/api/memories').status_code==401
        headers={'X-Pacoca-Token':app.state.token}
        assert c.get('/api/memories',headers=headers).status_code==200
        assert c.get('/api/memories',headers={**headers,'Origin':'https://evil.example'}).status_code==403
        assert c.get('/api/memories',headers={**headers,'Host':'evil.example'}).status_code==403


def test_api_full_conversation_and_memory_crud(tmp_path):
    app=create_app(Settings(tmp_path),FakeRuntime(),start_engine=False)
    with TestClient(app) as c:
        c.headers['X-Pacoca-Token']=app.state.token
        cid=c.post('/api/conversations').json()['id']
        assert c.get('/api/conversations/'+cid).json()['messages']==[]
        m=c.post('/api/memories',json={'content':'Meu projeto é Paçoca.'}).json()['id']
        assert len(c.get('/api/memories').json())==1
        c.patch('/api/memories/'+m,json={'content':'Minha assistente é Paçoca.'})
        assert c.get('/api/memories').json()[0]['content']=='Minha assistente é Paçoca.'
        c.delete('/api/memories/'+m)
        assert c.get('/api/memories').json()==[]
        c.delete('/api/conversations/'+cid)
        assert c.get('/api/conversations/'+cid).status_code==404


def test_knowledge_root_removal_revokes_search_and_file_access(tmp_path):
    app=create_app(Settings(tmp_path/'app'),FakeRuntime(),start_engine=False)
    root=tmp_path/'docs';root.mkdir();(root/'note.md').write_text('Paçoca obra orçamento',encoding='utf-8')
    with TestClient(app) as c:
        c.headers['X-Pacoca-Token']=app.state.token
        assert c.post('/api/knowledge/roots',json={'path':str(root)}).status_code==200
        index_folder(app.state.settings,app.state.store,str(root))
        assert c.get('/api/knowledge/search?q=orçamento').json()
        c.request('DELETE','/api/knowledge/roots',json={'path':str(root)})
        assert c.get('/api/knowledge/search?q=orçamento').json()==[]
        with pytest.raises(PermissionError):
            app.state.settings.resolve_path(str(root/'note.md'))


def test_recovery_never_replays_interrupted_tasks(service):
    _,store,_=service
    id=store.task(store.conversation()['id'],'Uma escrita pendente')
    store.recover()
    assert store.query('SELECT status FROM tasks WHERE id=?',(id,))[0]['status']=='interrupted'


@pytest.mark.asyncio
async def test_action_request_cannot_be_satisfied_by_an_ungrounded_text_reply(service):
    settings,store,tools=service
    class Ungrounded(FakeRuntime):
        async def select_tool(self,messages,schemas):
            return 'write_file'
    runtime=Ungrounded([[{'delta':{'content':'Salvei o arquivo com sucesso.'},'finish_reason':'stop'}]])
    service=Conversations(settings,store,runtime,tools,None)
    id=await service.submit(store.conversation()['id'],'Salve um arquivo')
    await service.runs[id].task
    task=store.query('SELECT * FROM tasks WHERE id=?',(id,))[0]
    assert task['status']=='failed'
    assert 'Nenhuma ação foi executada' in task['output']
    assert not list(settings.workspace.iterdir())


@pytest.mark.asyncio
async def test_interrupted_completed_audio_is_marked_as_partially_heard(service):
    from pacoca.conversation import Run
    settings,store,tools=service
    service=Conversations(settings,store,FakeRuntime(),tools,None)
    cid=store.conversation()['id']
    mid=store.message(cid,'assistant','Uma fala que ainda não terminou de tocar.')
    run=Run('voice-run',cid,'Oi',True,assistant_id=mid,audio_sent=2,finished=True)
    await service.cancel_run(run)
    assert store.messages(cid)[0]['interrupted']==1


def test_task_history_preserves_observed_steps_after_restart(service):
    _,store,tools=service
    id=store.task(store.conversation()['id'],'Consultar sistema e depois criar arquivo')
    store.event(id,'tool',{'name':'computer_info','result':{'ok':True,'data':{'memory_total_gb':32}}})
    store.recover()
    result=tools._execute_sync('task_history',tools.validate('task_history',{'id':id}))
    assert result[0]['status']=='interrupted'
    assert result[0]['steps'][0]['data']['result']['data']['memory_total_gb']==32


@pytest.mark.asyncio
async def test_browser_rejects_internal_networks(service):
    _,_,tools=service
    with pytest.raises(PermissionError):
        await tools.browser.validate_url('http://127.0.0.1:7755')
    with pytest.raises(ValueError):
        await tools.browser.validate_url('file:///etc/passwd')
    with pytest.raises(ValueError):
        await tools.browser.validate_url('https://user:password@example.com')
