import base64
import hashlib
import io
import json
import zipfile

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa

from pacoca.config import Settings
from pacoca.resources import ResourcePolicy
from pacoca.update_format import application_path,decode_manifest,validate_package
from pacoca.updates import UpdateManager,runtime_identity,render_helper,helper_encoded_command


@pytest.fixture(scope='module')
def publisher():
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    n=private.public_key().public_numbers()
    def enc(v):return base64.b64encode(v.to_bytes((v.bit_length()+7)//8,'big')).decode()
    return private,{'modulus':enc(n.n),'exponent':enc(n.e)}


def signed(payload,publisher):
    data=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    return {'signed':base64.b64encode(data).decode(),'signature':base64.b64encode(
        publisher[0].sign(data,padding.PKCS1v15(),hashes.SHA256())).decode()}


def release(publisher,version='1.1.1',bad_path=None):
    body=b'not executed in format tests'
    path=bad_path or 'Pacoca.exe'
    metadata={'version':version,'runtime_id':runtime_identity(),
              'files':[{'path':path,'size':len(body),'sha256':hashlib.sha256(body).hexdigest()}],'remove':[]}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr(path,body);z.writestr('package.json',json.dumps(metadata))
    data=stream.getvalue()
    package={'kind':'app','from_runtime':runtime_identity(),'runtime_id':runtime_identity(),
        'url':'https://github.com/AthirsonLamonato/Pacoca/releases/download/v1.1.1/app.zip',
        'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    payload={'schema':1,'app_id':'pacoca-desktop','database_schema':1,'version':version,'packages':[package]}
    return signed(payload,publisher),payload,data


def test_modified_manifest_signature_is_rejected(publisher):
    envelope,_,_=release(publisher)
    data=base64.b64decode(envelope['signed']).replace(b'1.1.1',b'9.9.9')
    envelope['signed']=base64.b64encode(data).decode()
    with pytest.raises(InvalidSignature):decode_manifest(envelope,publisher[1])


@pytest.mark.parametrize('path',['../Pacoca.exe','/Pacoca.exe','C:/Pacoca.exe','_internal/../secret',
    'assets/models/chat.gguf','Workspace/notes.txt','_internal/CON.txt','_internal/name:stream','_internal/dir./file'])
def test_update_cannot_escape_code_or_touch_models_and_data(path):
    with pytest.raises(ValueError):application_path(path)


def test_archive_path_traversal_is_rejected_before_extracting(tmp_path,publisher):
    _,payload,data=release(publisher,bad_path='_internal/../../outside.txt')
    archive=tmp_path/'update.zip';archive.write_bytes(data)
    with pytest.raises(ValueError):validate_package(archive,payload['packages'][0],payload['version'])
    assert not (tmp_path/'outside.txt').exists()


def test_package_corruption_is_rejected(tmp_path,publisher):
    _,payload,data=release(publisher)
    archive=tmp_path/'update.zip';archive.write_bytes(data+b'x')
    with pytest.raises(ValueError):validate_package(archive,payload['packages'][0],payload['version'])


async def manager(tmp_path,publisher,busy=lambda:'',games=None):
    envelope,payload,data=release(publisher)
    def handle(request):
        if request.url.path.endswith('manifest.json'):return httpx.Response(200,json=envelope)
        return httpx.Response(200,content=data)
    settings=Settings(tmp_path/'data')
    policy=ResourcePolicy(settings,lambda:games or [])
    async def emit(*args,**kwargs):pass
    client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    service=UpdateManager(settings,policy,emit,busy,root=tmp_path/'app',
        feed='https://github.com/AthirsonLamonato/Pacoca/releases/latest/download/manifest.json',
        key=publisher[1],version='1.1.0',client=client)
    return service,payload


@pytest.mark.asyncio
async def test_verified_download_does_not_install_during_voice(tmp_path,publisher):
    service,_=await manager(tmp_path,publisher,busy=lambda:'Conversa ativa')
    launched=[];service.launch=lambda *a:launched.append(a)
    await service.check();await service.download()
    assert service.state['phase']=='ready'
    assert (await service.apply())['ok'] is False
    assert not launched
    await service.close()


@pytest.mark.asyncio
async def test_game_blocks_installation_even_when_app_is_exiting(tmp_path,publisher):
    service,_=await manager(tmp_path,publisher)
    await service.check();await service.download()
    service.policy.games=lambda:['cs2.exe']
    assert not (await service.apply(exiting=True))['ok']
    await service.close()


@pytest.mark.asyncio
async def test_failed_version_is_not_automatically_retried(tmp_path,publisher):
    service,payload=await manager(tmp_path,publisher)
    (service.cache/'last-result.json').write_text(json.dumps({'status':'rolled_back','version':payload['version']}))
    await service.check()
    assert service.state['phase']=='failed' and not service.package
    await service.close()


@pytest.mark.asyncio
async def test_verified_package_launches_helper_only_when_idle(tmp_path,publisher):
    service,_=await manager(tmp_path,publisher)
    launched=[];service.launch=lambda script,job:launched.append((script,json.loads(job.read_text())))
    await service.check();await service.download()
    assert (await service.apply())['ok']
    assert len(launched)==1 and launched[0][1]['install_root']==str((tmp_path/'app').resolve())
    assert 'ExecutionPolicy' not in launched[0][0] and 'Invoke-Expression' not in launched[0][0]
    assert len(helper_encoded_command(launched[0][0]))<30000
    await service.close()


@pytest.mark.asyncio
async def test_first_check_runs_even_soon_after_windows_boot(tmp_path,publisher,monkeypatch):
    import asyncio
    import pacoca.updates as module
    service,_=await manager(tmp_path,publisher)
    monkeypatch.setattr(module.time,'monotonic',lambda:100)
    calls=[]
    async def checked():calls.append(True);raise asyncio.CancelledError
    async def instant_sleep(_):pass
    service.check=checked
    monkeypatch.setattr(module.asyncio,'sleep',instant_sleep)
    with pytest.raises(asyncio.CancelledError):await service.loop()
    assert calls==[True]
    await service.close()
