import asyncio
from datetime import datetime,timezone,timedelta
import uuid

from fastapi.testclient import TestClient

from pacoca.app import create_app
from pacoca.config import Settings
from test_core import FakeRuntime


def request(kind="LaunchRequest",request_id=None):
    return {"context":{"System":{"application":{"applicationId":"skill"},"user":{"userId":"paired-user"}}},
            "request":{"type":kind,"requestId":request_id or uuid.uuid4().hex,
                       "timestamp":datetime.now(timezone.utc).isoformat(),"intent":{"name":"CommandIntent","slots":{"query":{"value":"Que horas são?"}}}}}


def app(tmp_path):
    settings=Settings(tmp_path)
    settings.update({"alexa_enabled":True,"alexa_skill_id":"skill","alexa_user_id":"paired-user"})
    return create_app(settings,FakeRuntime(),start_engine=False)


def test_alexa_is_disabled_until_configured(tmp_path):
    a=create_app(Settings(tmp_path),FakeRuntime(),start_engine=False)
    with TestClient(a) as c:
        assert c.post('/alexa',json=request()).status_code==404


def test_alexa_rejects_unsigned_request(tmp_path):
    with TestClient(app(tmp_path)) as c:
        assert c.post('/alexa',json=request()).status_code==403


def test_alexa_rejects_unpaired_user_before_signature_fetch(tmp_path):
    data=request();data['context']['System']['user']['userId']='another-user'
    with TestClient(app(tmp_path)) as c:
        assert c.post('/alexa',json=data).status_code==403


def test_alexa_rejects_expired_timestamp(tmp_path):
    data=request();data['request']['timestamp']=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
    with TestClient(app(tmp_path)) as c:
        assert c.post('/alexa',json=data).status_code==403


def test_validated_alexa_request_is_queued_once(tmp_path):
    a=app(tmp_path)
    async def verified(headers,body):
        pass
    a.state.alexa_verify=verified
    data=request('IntentRequest','same-request')
    with TestClient(a) as c:
        result=c.post('/alexa',json=data)
        assert result.status_code==200
        assert 'Recebi' in result.json()['response']['outputSpeech']['text']
        duplicate=c.post('/alexa',json=data)
        assert 'já foi recebido' in duplicate.json()['response']['outputSpeech']['text']
        assert len(a.state.store.query('SELECT * FROM alexa_requests'))==1


def test_alexa_stop_does_not_cancel_desktop_tasks(tmp_path):
    a=app(tmp_path)
    async def verified(headers,body):pass
    a.state.alexa_verify=verified
    data=request('IntentRequest');data['request']['intent']['name']='AMAZON.StopIntent'
    with TestClient(a) as c:
        result=c.post('/alexa',json=data)
        assert result.status_code==200
        assert result.json()['response']['shouldEndSession']
