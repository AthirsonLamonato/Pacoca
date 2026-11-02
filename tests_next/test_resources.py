import json
from pathlib import Path

import pytest

from pacoca.audio import Voice
from pacoca.config import Settings
from pacoca.resources import ResourcePolicy
from pacoca.runtime import LocalRuntime


def test_existing_install_migrates_to_light_without_deleting_models(tmp_path):
    (tmp_path/'settings.json').write_text(json.dumps({'backend':'auto','context_size':8192,'user_name':'Athy'}))
    model=tmp_path/'model.gguf';model.write_bytes(b'keep')
    settings=Settings(tmp_path)
    assert settings.get('model_profile')=='light'
    assert settings.get('context_size')==4096
    assert settings.get('user_name')=='Athy' and model.read_bytes()==b'keep'


def test_advanced_profile_is_suspended_while_a_game_is_running(tmp_path):
    settings=Settings(tmp_path);settings.update({'model_profile':'advanced'})
    processes=['VALORANT-Win64-Shipping.exe','explorer.exe']
    clock=[0]
    policy=ResourcePolicy(settings,lambda:processes,lambda:clock[0])
    assert policy.profile()=='light'
    processes[:]=['explorer.exe'];clock[0]=3
    assert policy.profile()=='advanced'


@pytest.mark.asyncio
async def test_start_and_status_do_not_load_any_inference_or_audio_process(tmp_path,monkeypatch):
    assets=tmp_path/'assets';assets.mkdir()
    (assets/'manifest.json').write_text(json.dumps({'name':'Light','model':'models/light.gguf',
        'models':{'light':{'name':'Light','path':'models/light.gguf'},'advanced':{'name':'8B','path':'models/8b.gguf'}}}))
    monkeypatch.setenv('PACOCA_ASSETS',str(assets))
    runtime=LocalRuntime(Settings(tmp_path/'data'))
    await runtime.start()
    voice=Voice(runtime,runtime.settings)
    assert runtime.info()['status']=='sleeping'
    assert runtime.process is None and not voice.info()['pid']
    assert not voice.info()['tts_loaded'] and not voice.info()['stt_loaded']
    voice.close();await runtime.close()


@pytest.mark.asyncio
async def test_missing_light_model_never_falls_back_silently_to_8b(tmp_path,monkeypatch):
    assets=tmp_path/'assets';assets.mkdir()
    (assets/'heavy.gguf').write_bytes(b'heavy')
    (assets/'manifest.json').write_text(json.dumps({'name':'8B','model':'heavy.gguf'}))
    monkeypatch.setenv('PACOCA_ASSETS',str(assets))
    runtime=LocalRuntime(Settings(tmp_path/'data'))
    with pytest.raises(FileNotFoundError):await runtime.ensure_ready()
    assert runtime.process is None
    await runtime.close()


def test_model_path_cannot_escape_asset_directory(tmp_path,monkeypatch):
    assets=tmp_path/'assets';assets.mkdir()
    (assets/'manifest.json').write_text('{}')
    monkeypatch.setenv('PACOCA_ASSETS',str(assets))
    # The existing resource path gate also applies to audio worker resources.
    from pacoca.audio import _Assets
    with pytest.raises(FileNotFoundError):_Assets(assets,{'voice':'../outside'}).resource('voice')
