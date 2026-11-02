"""Start a distribution with no development environment on its PATH and verify it.

Uses disposable data. Does not record a human microphone or modify the user's apps.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import psutil

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--name', default='distribution')
    parser.add_argument('--native', action='store_true')
    parser.add_argument('--keep-running', action='store_true')
    args = parser.parse_args()
    data = ROOT / '.test-data' / args.name
    data.mkdir(parents=True, exist_ok=True)
    connection = data / 'connection.json'
    connection.unlink(missing_ok=True)
    native_ready = data / 'native-ready.json'
    native_ready.unlink(missing_ok=True)
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'PACOCA_ASSETS', 'PLAYWRIGHT_BROWSERS_PATH'):
        env.pop(key, None)
    system_root = os.environ.get('SystemRoot', r'C:\Windows')
    env['PATH'] = ';'.join([str(Path(system_root) / 'System32'), system_root,
        str(Path(system_root) / 'System32/WindowsPowerShell/v1.0')])
    env['PACOCA_DATA'] = str(data)
    if args.assets:
        env['PACOCA_ASSETS'] = str(args.assets.resolve())
    command = [str(args.exe.resolve()), '--connection-file', str(connection)]
    if not args.native:
        command.append('--headless')
    else:
        command.extend(['--native-ready-file',str(native_ready)])
    process = subprocess.Popen(command, cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    client = None
    passed = False
    try:
        deadline = time.monotonic() + 180
        while not connection.exists():
            if process.poll() is not None:
                raise RuntimeError(f'Distribution exited: {process.returncode}')
            if time.monotonic() > deadline:
                raise TimeoutError('No distribution connection file')
            time.sleep(.5)
        config = json.loads(connection.read_text(encoding='utf-8'))
        client = httpx.Client(base_url=f"http://127.0.0.1:{config['port']}",
                              headers={'X-Pacoca-Token': config['token']}, timeout=120, trust_env=False)
        if args.native:
            window_deadline=time.monotonic()+40
            while not native_ready.exists():
                if process.poll() is not None:
                    raise RuntimeError('Native window exited before rendering')
                if time.monotonic()>window_deadline:
                    raise TimeoutError('Qt window did not render; an HTTP server alone is not a native UI test')
                time.sleep(.5)
            assert json.loads(native_ready.read_text())['rendered']
        while True:
            try:
                status = client.get('/api/status').json()
                if status['engine']['status'] in ('sleeping','ready'):
                    break
                if status['engine']['status'] == 'error':
                    raise RuntimeError(status['engine'])
            except httpx.ConnectError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError('Distribution engine not ready')
            time.sleep(1)
        assert client.get('/').status_code == 200
        assert not status['engine']['loaded'] and not status['voice']['pid'],status
        root=psutil.Process(process.pid)
        children=[root,*root.children(recursive=True)]
        idle_rss=sum(p.memory_info().rss for p in children if p.is_running())
        cpu_before=sum(p.cpu_times().user+p.cpu_times().system for p in children if p.is_running())
        time.sleep(3)
        cpu_after=sum(p.cpu_times().user+p.cpu_times().system for p in children if p.is_running())
        idle_cpu=(cpu_after-cpu_before)/3/psutil.cpu_count()*100
        capabilities=client.get('/api/actions/capabilities').json()
        assert capabilities.get('ocr') and capabilities.get('media'),capabilities
        catalog=client.get('/api/applications').json()
        assert isinstance(catalog,list) and catalog,catalog
        cid = client.post('/api/conversations').json()['id']
        task_id = client.post('/api/chat', json={'conversation_id': cid,
            'text': 'Oi! Quem é você? Responda em uma frase.', 'voice': True}).json()['run_id']
        while True:
            task = client.get('/api/tasks/' + task_id).json()
            if task['status'] not in ('running', 'waiting_approval'):
                break
            if time.monotonic() > deadline + 120:
                raise TimeoutError('Distribution conversation')
            time.sleep(.5)
        assert task['status'] == 'completed', task
        executed_backend=client.get('/api/status').json()['engine']['backend']
        speech = client.post('/api/voice/preview')
        assert speech.status_code == 200 and speech.content[:4] == b'RIFF'
        # A second launch must activate the original process and exit.
        second = subprocess.run(command, cwd=ROOT, env=env, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        assert second.returncode == 0
        assert json.loads(connection.read_text(encoding='utf-8'))['pid'] == process.pid
        report = {'executable': str(args.exe.resolve()), 'backend': executed_backend,
                  'development_path_removed': True, 'external_assets_override': bool(args.assets),
                  'native_window': args.native, 'native_rendered':bool(args.native and native_ready.exists()),
                  'conversation': task['output'],
                  'lazy_model_and_audio':True,'native_ocr_and_media':capabilities,
                  'installed_application_catalog_count':len(catalog),
                  'idle_all_processes_rss_mb':round(idle_rss/2**20),'idle_cpu_percent_of_host':round(idle_cpu,2),
                  'synthesized_wav_bytes': len(speech.content),
                  'single_instance': True}
        (ROOT / '.test-data/evidence' / (args.name + '.json')).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True), flush=True)
        passed = True
    finally:
        if not args.keep_running or not passed:
            if client:
                try:
                    client.post('/api/shutdown')
                    process.wait(timeout=40)
                except (httpx.HTTPError, subprocess.TimeoutExpired):
                    process.terminate()
            elif process.poll() is None:
                process.terminate()
        if client:
            client.close()


if __name__ == '__main__':
    main()
