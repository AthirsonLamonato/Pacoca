import io
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pacoca.app import create_app
from pacoca.audio import _LocalVoice
from pacoca.config import Settings
from test_core import FakeRuntime


def test_female_voice_does_not_load_piper_and_switching_preserves_stt(tmp_path, monkeypatch):
    settings=Settings(tmp_path); settings.update({'voice_style':'female'})
    voice=_LocalVoice(None,settings); voice.whisper=object(); voice.piper=object()
    sentinel=voice.whisper
    seen=[]
    monkeypatch.setattr('pacoca.audio.synthesize_female',lambda text,speed:seen.append((text,speed)) or b'RIFFtest')
    assert voice.synthesize('**Olá.**')==b'RIFFtest'
    assert seen==[('Olá.',1)] and voice.piper is None and voice.whisper is sentinel


def test_preview_respects_unsaved_voice_without_changing_preferences(tmp_path, monkeypatch):
    calls=[]
    def synthesize(self,text,options=None):
        calls.append(options); return b'RIFFtest'
    monkeypatch.setattr('pacoca.audio.Voice.synthesize',synthesize)
    app=create_app(Settings(tmp_path),FakeRuntime(),start_engine=False)
    with TestClient(app) as client:
        headers={'X-Pacoca-Token':app.state.token}
        r=client.post('/api/voice/preview',headers=headers,json={'voice_style':'female','voice_speed':1.2})
        assert r.status_code==200 and calls[-1]=={'voice_style':'female','voice_speed':1.2}
        assert app.state.settings.get('voice_style')=='male'
        assert client.post('/api/voice/preview',headers=headers,json={'voice_style':'anything'}).status_code==422


def test_female_preference_is_rejected_when_windows_voice_is_missing(tmp_path,monkeypatch):
    monkeypatch.setattr('pacoca.audio.female_voices',lambda:())
    app=create_app(Settings(tmp_path),FakeRuntime(),start_engine=False)
    with TestClient(app) as client:
        r=client.patch('/api/settings',headers={'X-Pacoca-Token':app.state.token},json={'voice_style':'female'})
        assert r.status_code==422 and app.state.settings.get('voice_style')=='male'


def test_transcription_switch_releases_previous_model(tmp_path,monkeypatch):
    import numpy as np
    import faster_whisper
    paths=[]
    class Model:
        def __init__(self,path,**kwargs):paths.append(path)
        def transcribe(self,audio,**kwargs):return iter([SimpleNamespace(text='abre o Spotify')]),None
    monkeypatch.setattr(faster_whisper,'WhisperModel',Model)
    quick=tmp_path/'quick'
    monkeypatch.setattr('pacoca.audio.fast_model',lambda:quick)
    settings=Settings(tmp_path)
    voice=_LocalVoice(SimpleNamespace(resource=lambda _:tmp_path/'precise'),settings)
    pcm=np.ones(16000,dtype=np.float32)
    voice.transcribe(pcm); voice.transcribe(pcm)
    settings.update({'transcription_mode':'precise'}); voice.transcribe(pcm)
    assert paths==[str(quick),str(tmp_path/'precise')]


@pytest.mark.skipif(__import__('os').name!='nt',reason='Windows offline voices')
def test_native_female_wav_without_playback():
    from pacoca.native_voice import female_voices,synthesize_female
    if not female_voices():pytest.skip('No Brazilian female voice installed')
    with wave.open(io.BytesIO(synthesize_female('Olá, eu sou a Paçoca.',1))) as wav:
        assert wav.getframerate()==16000 and wav.getnchannels()==1 and wav.getnframes()>1600
