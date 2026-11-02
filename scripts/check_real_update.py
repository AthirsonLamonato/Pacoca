"""Upgrade an isolated, real Qt distribution through the signed local QA feed."""
import functools
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx
import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pacoca.config import Settings
from pacoca.store import Store
from pacoca.update_format import sha256


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def main():
    base=ROOT/'.test-data/updater-real';root=base/'app';data=base/'data'
    settings=Settings(data);settings.update({'onboarding_done':True,'idle_seconds':15,'updates_enabled':True})
    store=Store(data/'pacoca.sqlite3')
    marker='Lembrança preservada na atualização real 1.1'
    if not store.memories():store.remember(marker)
    store.close()
    manifest=json.loads((root/'assets/manifest.json').read_text())
    model=root/'assets'/manifest['model'];model_before=(model.stat().st_size,model.stat().st_mtime_ns)
    evidence=ROOT/'.test-data/evidence';evidence.mkdir(exist_ok=True)
    # Bind first; every package URL and the manifest are signed for this QA server.
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(base/'feed')))
    feed=f'http://127.0.0.1:{server.server_port}'
    subprocess.run([sys.executable,'scripts/package_update.py','--app-only','--output',str(base/'feed'),'--base-url',feed],cwd=ROOT,check=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    connection=data/'instance.json';connection.unlink(missing_ok=True)
    for p in [data/'Updates/last-result.json']:p.unlink(missing_ok=True)
    env=os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','PACOCA_ASSETS'):env.pop(key,None)
    windows=Path(os.environ.get('SystemRoot',r'C:\Windows'))
    env['PATH']=';'.join(str(p) for p in (windows/'System32',windows,windows/'System32/WindowsPowerShell/v1.0'))
    env['PACOCA_DATA']=str(data)
    started=time.monotonic();process=subprocess.Popen([str(root/'Pacoca.exe'),'--update-feed',feed+'/desktop-update.json'],env=env,cwd=root,creationflags=subprocess.CREATE_NO_WINDOW)
    client=None;new_client=None;phases=[]
    try:
        deadline=time.monotonic()+200
        while not connection.exists():
            if process.poll() is not None:raise RuntimeError('Baseline exited before startup')
            if time.monotonic()>deadline:raise TimeoutError('Baseline startup')
            time.sleep(.25)
        old=json.loads(connection.read_text())
        client=httpx.Client(base_url=f"http://127.0.0.1:{old['port']}",headers={'X-Pacoca-Token':old['token']},trust_env=False,timeout=10)
        initial=client.get('/api/status').json()
        assert initial['version']=='1.1.0' and not initial['engine']['loaded']
        # This QA prototype predates the cold-boot check fix; initiate its first check.
        client.post('/api/updates/check').raise_for_status()
        receipt=data/'Updates/last-result.json'
        while not receipt.exists():
            try:
                state=client.get('/api/updates').json()
                if not phases or phases[-1]!=state['phase']:phases.append(state['phase']);print('UPDATE',state['phase'],flush=True)
                if state['phase'] in ('failed','error'):raise RuntimeError(state)
            except httpx.HTTPError:pass
            if time.monotonic()>deadline:raise TimeoutError('Real updater transaction')
            time.sleep(.5)
        result=json.loads(receipt.read_text(encoding='utf-8-sig'))
        assert result['status']=='installed',result
        health=json.loads((Path(result['transaction'])/'health.json').read_text())
        assert health['rendered'] and health['version']=='1.1.1' and health['pid']!=process.pid
        current=json.loads(connection.read_text())
        new_client=httpx.Client(base_url=f"http://127.0.0.1:{current['port']}",headers={'X-Pacoca-Token':current['token']},trust_env=False,timeout=10)
        status=new_client.get('/api/status').json()
        assert status['version']=='1.1.1' and not status['engine']['loaded'] and not status['voice']['pid']
        assert any(m['content']==marker for m in new_client.get('/api/memories').json())
        assert (model.stat().st_size,model.stat().st_mtime_ns)==model_before
        assert (Path(result['transaction'])/'database.sqlite3').exists()
        new_client.post('/api/shutdown');new_client.close();new_client=None
        psutil.Process(health['pid']).wait(timeout=40)
        # The released updater must check immediately even on a recently booted PC.
        connection.unlink(missing_ok=True)
        cold=subprocess.Popen([str(root/'Pacoca.exe'),'--update-feed',feed+'/desktop-update.json'],env=env,cwd=root,creationflags=subprocess.CREATE_NO_WINDOW)
        while not connection.exists():
            if time.monotonic()>deadline:raise TimeoutError('Updated cold startup')
            time.sleep(.2)
        current=json.loads(connection.read_text())
        new_client=httpx.Client(base_url=f"http://127.0.0.1:{current['port']}",headers={'X-Pacoca-Token':current['token']},trust_env=False,timeout=10)
        while new_client.get('/api/updates').json()['phase']!='current':
            if time.monotonic()>deadline:raise TimeoutError('Initial automatic check after a recent Windows boot')
            time.sleep(.4)
        report={'from':'1.1.0','to':'1.1.1','seconds':round(time.monotonic()-started,2),'phases':phases,
            'actual_qt_health':health,'baseline_initial_check':'explicit API; old QA prototype',
            'automatic_download_install':True,'signed_manifest':True,
            'final_cold_automatic_check':True,
            'model_untouched':True,'memory_preserved':True,'sqlite_backup':True,'no_inference_on_restart':True,
            'human_microphone':False,'public_github_feed':False}
        (evidence/'real-update.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
    finally:
        for handle in (new_client,client):
            if handle:
                try:handle.post('/api/shutdown')
                except httpx.HTTPError:pass
                handle.close()
        process.wait(timeout=40)
        # Only this isolated executable's remaining health process may be stopped.
        for p in psutil.process_iter(['exe']):
            try:
                if p.info['exe'] and Path(p.info['exe']).resolve()==(root/'Pacoca.exe').resolve():p.wait(15)
            except psutil.TimeoutExpired:p.terminate();p.wait(10)
            except psutil.Error:pass
        server.shutdown();server.server_close()


if __name__=='__main__':main()
