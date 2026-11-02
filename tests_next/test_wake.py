import json
from pathlib import Path
import time
import wave

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from pacoca.app import create_app
from pacoca.config import Settings
from pacoca.wake import KeywordDetector, WakeService
from test_core import FakeRuntime


FIXTURES = Path(__file__).parent / 'fixtures/wake'
CASES = json.loads((FIXTURES / 'cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=[c['file'] for c in CASES])
def test_real_detector_generated_portuguese_speech(case):
    detector = KeywordDetector()
    with wave.open(str(FIXTURES / case['file'])) as wav:
        audio = wav.readframes(wav.getnframes())
    found = []
    for at in range(0, len(audio), 5120):
        result = detector.feed(audio[at:at+5120])
        if result['type'] == 'wake': found.append(result)
    assert bool(found) == case['wake'], case['text']
    if found:
        assert len(found) == 1
        assert 0 <= found[0]['start'] < found[0]['end'] <= found[0]['samples']


def test_detector_reset_drops_previous_keyword():
    detector = KeywordDetector()
    with wave.open(str(FIXTURES / '01.wav')) as wav:
        pcm = wav.readframes(wav.getnframes())
    detector.feed(pcm[:5120]); detector.reset()
    for _ in range(150): assert detector.feed(bytes(5120))['type'] == 'ack'
    assert detector.samples == 384000


def test_worker_is_lazy_exclusive_and_can_be_released(tmp_path):
    settings = Settings(tmp_path)
    service = WakeService(settings)
    assert service.info()['pid'] is None
    with pytest.raises(RuntimeError): service.open('one')
    settings.update({'wake_enabled': True})
    assert service.open('one')['type'] == 'ready'
    with pytest.raises(RuntimeError): service.open('two')
    service.close('two')
    assert service.info()['pid']
    assert service.feed('one', bytes(5120))['type'] == 'ack'
    with pytest.raises(ValueError): service.feed('one', bytes(20000))
    with pytest.raises(ValueError): service.feed('one', b'x')
    service.close('one')
    assert service.info()['pid'] is None


def test_audio_websocket_auth_pause_and_invalid_frame(tmp_path):
    settings = Settings(tmp_path)
    app = create_app(settings, FakeRuntime(), start_engine=False)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/wake?token=wrong'): pass
        url = '/wake?token=' + app.state.token
        with client.websocket_connect(url) as ws:
            assert ws.receive_json()['type'] == 'error'
        headers = {'X-Pacoca-Token': app.state.token}
        assert client.patch('/api/settings', headers=headers, json={'wake_timeout': 5}).status_code == 422
        client.patch('/api/settings', headers=headers, json={'wake_enabled': True})
        with client.websocket_connect(url) as ws:
            assert ws.receive_json()['type'] == 'ready'
            ws.send_bytes(bytes(5120))
            assert ws.receive_json()['samples'] == 2560
            ws.send_text('reset'); assert ws.receive_json()['type'] == 'reset'
            ws.send_bytes(bytes(12000)); assert ws.receive_json()['type'] == 'error'
        client.post('/api/stop', headers=headers)
        assert not settings.get('wake_enabled')
        assert app.state.wake.info()['pid'] is None


def test_standby_does_not_block_update_but_activation_does(tmp_path):
    app = create_app(Settings(tmp_path), FakeRuntime(), start_engine=False)
    with TestClient(app):
        app.state.wake.active_until = time.monotonic()+8
        assert app.state.updates.busy()
        app.state.wake.active_until = 0
        assert not app.state.updates.busy()
