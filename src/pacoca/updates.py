"""Signed updates, independent of the AI models and active desktop sessions."""
from __future__ import annotations

import asyncio
import ctypes
import hashlib
import base64
import gzip
import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx
from packaging.version import Version

from . import __version__
from .update_format import decode_manifest, sha256, validate_package
from .update_trust import PUBLIC_KEY
from .resources import GAME_PROCESSES

log=logging.getLogger(__name__)
FEED='https://github.com/AthirsonLamonato/Pacoca/releases/latest/download/desktop-update.json'


def runtime_identity():
    path=Path(__file__).with_name('runtime-id.txt')
    return path.read_text(encoding='utf-8').strip() if path.exists() else 'development'


def allowed_url(url,local=False):
    parsed=urlparse(url)
    if parsed.username or parsed.password or parsed.fragment:raise ValueError('Invalid update URL')
    if local and parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost'):
        return url
    if parsed.scheme!='https' or parsed.hostname!='github.com' or not parsed.path.startswith('/AthirsonLamonato/Pacoca/releases/'):
        raise ValueError('Update URL is not in the official release channel')
    return url


def render_helper(root,data,key=PUBLIC_KEY):
    script=Path(__file__).with_name('update_helper.ps1').read_text(encoding='utf-8')
    return script.replace('__PUBLIC_KEY_JSON__',json.dumps(key,separators=(',',':'))).replace(
        '__TRUSTED_ROOT__',str(root).replace("'","''")).replace('__TRUSTED_DATA__',str(data).replace("'","''"))


def helper_encoded_command(script):
    # Compression only packages this fixed local script within Windows' argv limit.
    packed=base64.b64encode(gzip.compress(script.encode('utf-8'))).decode()
    loader=("$b=[Convert]::FromBase64String('"+packed+"');"
        "$m=[IO.MemoryStream]::new($b);$g=[IO.Compression.GZipStream]::new($m,[IO.Compression.CompressionMode]::Decompress);"
        "$r=[IO.StreamReader]::new($g,[Text.Encoding]::UTF8);$s=$r.ReadToEnd();$r.Dispose();"
        "& ([ScriptBlock]::Create($s))")
    return base64.b64encode(loader.encode('utf-16le')).decode()


class UpdateManager:
    def __init__(self,settings,policy,emit,busy,*,root=None,feed=FEED,key=PUBLIC_KEY,version=__version__,client=None):
        self.settings,self.policy,self.emit,self.busy=settings,policy,emit,busy
        self.root=Path(root or Path(sys.executable).parent).resolve()
        self.installed=bool(root or getattr(sys,'frozen',False))
        self.feed,self.key,self.version=feed,key,version
        self.local=urlparse(feed).hostname in ('127.0.0.1','localhost')
        allowed_url(feed,self.local)
        self.cache=settings.directory/'Updates';self.cache.mkdir(exist_ok=True)
        self.client=client or httpx.AsyncClient(timeout=httpx.Timeout(60,connect=10),follow_redirects=True,trust_env=False)
        self.lock=asyncio.Lock()
        self.state={'phase':'idle' if self.installed else 'development','installed':version,'version':'',
                    'percent':0,'message':'','installing':False,'can_install':self.installed}
        self.manifest=self.payload=self.package=None
        self.archive=None
        self.ready_since=0
        self.checking=self.downloading=None
        self.launch=None
        self.shutdown=None
        self.backup=None
        self.last_check=0

    def info(self):
        blocker=self.blocker()
        return {**self.state,'blocked':blocker,'automatic':self.settings.get('updates_enabled',True),
                'install_on_exit':self.settings.get('update_install_on_exit',True)}

    def blocker(self):
        if self.policy.games():return 'Aguardando o jogo ser encerrado'
        return self.busy() or ''

    async def publish(self,**values):
        self.state.update(values)
        await self.emit('update',update=self.info())

    def previous_failure(self,version):
        path=self.cache/'last-result.json'
        try:
            last=json.loads(path.read_text(encoding='utf-8-sig'))
            return last.get('version')==version and last.get('status') in ('failed','rolled_back')
        except (OSError,ValueError):return False

    async def check(self):
        if not self.installed:return self.info()
        async with self.lock:
            if self.state['phase'] in ('ready','downloading','installing'):return self.info()
            self.last_check=time.monotonic()
            await self.publish(phase='checking',message='Procurando atualizações')
            try:
                response=await self.client.get(self.feed)
                if response.status_code==404:
                    await self.publish(phase='unavailable',message='O canal de atualização ainda não publicou uma versão compatível.')
                    return self.info()
                response.raise_for_status()
                if len(response.content)>4_000_000:raise ValueError('Manifesto de atualização grande demais')
                payload=decode_manifest(response.content,self.key)
                if Version(payload['version'])<=Version(self.version):
                    await self.publish(phase='current',version=payload['version'],message='Você está com a versão atual.')
                    return self.info()
                if self.previous_failure(payload['version']):
                    await self.publish(phase='failed',version=payload['version'],message='Essa versão falhou na última tentativa. Sua instalação anterior foi preservada.')
                    return self.info()
                identity=runtime_identity()
                options=[p for p in payload['packages'] if p['from_runtime']==identity]
                if not options:options=[p for p in payload['packages'] if p['from_runtime']=='*']
                if not options:raise ValueError('Não há pacote compatível com esta instalação')
                package=options[0];allowed_url(package['url'],self.local)
                self.manifest=json.loads(response.content)
                self.payload,self.package=payload,package
                await self.publish(phase='available',version=payload['version'],size=package['size'],
                                   notes=str(payload.get('notes',''))[:3000],message='Atualização disponível')
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
                log.warning('Update check failed: %s',type(exc).__name__)
                await self.publish(phase='error',message='Não consegui verificar uma atualização autêntica. Vou tentar mais tarde.')
            except Exception as exc:
                # Cryptographic signature failures must never reach installation.
                log.warning('Rejected update manifest: %s',type(exc).__name__)
                await self.publish(phase='error',message='A atualização não passou na verificação de assinatura.')
            return self.info()

    async def download(self):
        async with self.lock:
            if not self.package or not self.payload:raise ValueError('Verifique se existe uma atualização primeiro')
            if self.state['phase']=='ready':return self.info()
            version=self.payload['version']
            folder=self.cache/version;folder.mkdir(exist_ok=True)
            archive=folder/(self.package['sha256']+'.zip')
            part=archive.with_suffix('.part')
            await self.publish(phase='downloading',percent=0,message='Baixando atualização')
            try:
                if not archive.exists() or archive.stat().st_size!=self.package['size'] or await asyncio.to_thread(sha256,archive)!=self.package['sha256']:
                    start=part.stat().st_size if part.exists() else 0
                    if start>=self.package['size']:
                        part.unlink();start=0
                    headers={'Range':f'bytes={start}-'} if start else {}
                    async with self.client.stream('GET',self.package['url'],headers=headers) as response:
                        response.raise_for_status()
                        if response.status_code==206:
                            if not response.headers.get('content-range','').startswith(f'bytes {start}-'):
                                raise ValueError('Resposta de retomada inválida')
                        else:start=0
                        received=start;last=0
                        with part.open('ab' if start else 'wb') as output:
                            async for block in response.aiter_bytes(128*1024):
                                while self.policy.games():
                                    await self.publish(message='Download pausado enquanto você joga')
                                    await asyncio.sleep(5)
                                received+=len(block)
                                if received>self.package['size']:raise ValueError('Pacote excedeu o tamanho assinado')
                                output.write(block)
                                if time.monotonic()-last>.5:
                                    last=time.monotonic()
                                    await self.publish(percent=round(received/self.package['size']*100),message='Baixando atualização')
                    if received!=self.package['size'] or await asyncio.to_thread(sha256,part)!=self.package['sha256']:
                        part.unlink(missing_ok=True)
                        raise ValueError('A integridade do download não confere')
                    part.replace(archive)
                await asyncio.to_thread(validate_package,archive,self.package,version)
                self.archive=archive
                self.ready_since=time.monotonic()
                (folder/'manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')
                await self.publish(phase='ready',percent=100,message='Atualização pronta. Vou instalar quando você estiver livre.')
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning('Update download rejected: %s',type(exc).__name__)
                await self.publish(phase='error',message='O download não foi concluído ou não passou na verificação.')
            return self.info()

    async def apply(self,*,exiting=False):
        async with self.lock:
            if self.state['phase']!='ready' or not self.archive:return {'ok':False,'reason':'Atualização ainda não está pronta'}
            blocker='' if exiting else self.blocker()
            if self.policy.games():blocker='Aguardando o jogo ser encerrado'
            if blocker:return {'ok':False,'reason':blocker}
            await asyncio.to_thread(validate_package,self.archive,self.package,self.payload['version'])
            transaction=self.cache/('transaction-'+self.payload['version']+'-'+secrets.token_hex(5))
            transaction.mkdir()
            manifest=transaction/'manifest.json';manifest.write_text(json.dumps(self.manifest),encoding='utf-8')
            if self.backup:
                await asyncio.to_thread(self.backup,transaction/'database.sqlite3')
            job={'install_root':str(self.root),'data_root':str(self.settings.directory),'transaction':str(transaction),
                 'manifest':str(manifest),'archive':str(self.archive),'package_hash':self.package['sha256'],
                 'version':self.payload['version'],'pid':os.getpid(),'game_names':sorted(GAME_PROCESSES)}
            path=transaction/'job.json';path.write_text(json.dumps(job),encoding='utf-8')
            script=render_helper(self.root,self.settings.directory,self.key)
            await self.publish(phase='installing',installing=True,message='Aplicando atualização e reiniciando')
            try:
                if self.launch:self.launch(script,path)
                else:self.launch_helper(script,path)
            except Exception:
                await self.publish(phase='ready',installing=False,message='Não consegui iniciar a atualização. Sua instalação foi preservada.')
                raise
            if self.shutdown:self.shutdown()
            return {'ok':True}

    @staticmethod
    def launch_helper(script,job):
        if os.name!='nt':raise RuntimeError('O atualizador de desktop é exclusivo do Windows')
        # A fixed bundled script, not model-generated shell text. No policy bypass.
        powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        encoded=helper_encoded_command(script)
        if len(encoded)>30000:raise ValueError('Update helper exceeds Windows command line limit')
        env={**os.environ,'PACOCA_UPDATE_JOB':str(job)}
        env['PSModulePath']=str(powershell.parent/'Modules')
        kernel=ctypes.windll.kernel32
        kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
        kernel.SetDllDirectoryW.restype=ctypes.c_int
        kernel.SetDllDirectoryW(None)
        try:
            subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],env=env,
                creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        finally:
            if getattr(sys,'frozen',False):kernel.SetDllDirectoryW(str(sys._MEIPASS))

    async def loop(self):
        if not self.installed:return
        await asyncio.sleep(8)
        idle_since=None
        while True:
            try:
                if self.settings.get('updates_enabled',True):
                    if not self.last_check or time.monotonic()-self.last_check>6*3600:
                        await self.check()
                    if self.state['phase']=='available' and not self.policy.games():await self.download()
                    if self.state['phase']=='ready' and not self.blocker():
                        if idle_since is None:idle_since=time.monotonic()
                        if time.monotonic()-idle_since>20:await self.apply()
                    else:idle_since=None
                await asyncio.sleep(5)
            except asyncio.CancelledError:raise
            except Exception:
                log.exception('Updater deferred after a failure')
                await asyncio.sleep(60)

    async def close(self):
        await self.client.aclose()
