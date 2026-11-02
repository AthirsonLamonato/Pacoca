"""Synthetic microphone only: real keyword -> Whisper -> harmless local conversation.

With --exe, exercises the actual minimized Qt application. Otherwise tests the
development UI in Chromium, including pause, session expiry, and no double mic.
"""
import argparse
import audioop
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

import httpx
import psutil
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--split-pause', action='store_true')
    parser.add_argument('--settings-only', action='store_true')
    args = parser.parse_args()
    name = 'wake-native' if args.exe else 'wake-browser'
    data = ROOT / '.test-data' / name
    data.mkdir(parents=True, exist_ok=True)
    connection = data / 'connection.json'; connection.unlink(missing_ok=True)
    native_ready=data/'rendered.json';native_ready.unlink(missing_ok=True)
    # A long silent lead measures standby without loading transcription or chat.
    fake = data / 'microphone.wav'
    with wave.open(str(ROOT / 'tests_next/fixtures/wake/02.wav')) as w:
        speech = w.readframes(w.getnframes())
    if args.split_pause:
        with wave.open(str(ROOT/'tests_next/fixtures/wake/00.wav')) as w:
            call = w.readframes(w.getnframes())
        with wave.open(str(ROOT/'tests_next/fixtures/wake/pause-command.wav')) as w:
            command = audioop.ratecv(w.readframes(w.getnframes()),2,1,w.getframerate(),16000,None)[0]
        speech = call+bytes(32000*2)+command
    with wave.open(str(fake), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(bytes(32000*14) + speech + bytes(32000*90))
    (data / 'settings.json').write_text(json.dumps({'onboarding_done': True, 'wake_enabled': not args.settings_only,
        'wake_timeout': 10, 'updates_enabled': False, 'idle_seconds': 15}), encoding='utf-8')
    env = os.environ.copy()
    env.update(PACOCA_DATA=str(data), PACOCA_ASSETS=str(ROOT/'assets'), PYTHONPATH=str(ROOT/'src'),
        PLAYWRIGHT_BROWSERS_PATH=str(ROOT/'assets/browser'))
    flags = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
             '--use-file-for-fake-audio-capture='+str(fake), '--mute-audio']
    # Chromium flag strings need quotes around the Windows path with spaces.
    env['QTWEBENGINE_CHROMIUM_FLAGS'] = ' '.join('"'+x+'"' if ' ' in x else x for x in flags)
    command = [str(args.exe.resolve())] if args.exe else [sys.executable, str(ROOT/'run-pacoca.py'), '--headless']
    if args.exe:
        for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):
            env.pop(key,None)
        windows=Path(os.environ.get('SystemRoot',r'C:\Windows'))
        env['PATH']=';'.join(str(p) for p in (windows/'System32',windows,windows/'System32/WindowsPowerShell/v1.0'))
        if (args.exe.resolve().parent/'assets/manifest.json').is_file():env.pop('PACOCA_ASSETS',None)
        command += ['--minimized','--native-ready-file',str(native_ready)]
    process = subprocess.Popen(command+['--connection-file',str(connection)],env=env,cwd=ROOT,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    browser = client = None
    started = time.monotonic()
    try:
        while not connection.exists():
            if process.poll() is not None: raise RuntimeError('Application failed to start')
            if time.monotonic()-started > 40: raise TimeoutError('Connection')
            await asyncio.sleep(.3)
        c = json.loads(connection.read_text())
        client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{c['port']}",
            headers={'X-Pacoca-Token':c['token']}, timeout=120, trust_env=False)
        # Remove earlier synthetic runs from this disposable test profile only.
        for old in (await client.get('/api/conversations')).json():
            await client.delete('/api/conversations/'+old['id'])
        async with async_playwright() as playwright:
            page = None; errors = []
            if not args.exe:
                browser = await playwright.chromium.launch(headless=True,args=flags,
                    executable_path=str(next((ROOT/'assets/browser').glob('chromium-*/chrome-win64/chrome.exe'))))
                page = await browser.new_page(permissions=['microphone'],viewport={'width':1320,'height':900})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('console',lambda message: print('UI',message.text,flush=True) if message.type=='error' else None)
                async def transcript(response):
                    if response.url.endswith('/api/transcribe'): print('TRANSCRIPT',await response.text(),flush=True)
                page.on('response',transcript)
                await page.goto(c['url'])
                if args.settings_only:
                    await page.wait_for_function('() => Boolean(state.status)')
                    await page.evaluate('''async () => {
                        const get = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                        navigator.mediaDevices.getUserMedia = async options => {
                            await new Promise(resolve => setTimeout(resolve,200)); return get(options);
                        };
                        const pending = startVoice(); await refreshStatus(); await pending;
                    }''')
                    await page.wait_for_function('() => state.voice && Boolean(state.stream)')
                    await page.locator('[data-page=settings]').click()
                    await page.wait_for_function('() => document.querySelector("#setting-mic").options.length > 1')
                    device=await page.locator('#setting-mic option').nth(1).get_attribute('value')
                    await page.locator('#setting-mic').select_option(device)
                    await page.locator('#save-settings').click()
                    await page.wait_for_timeout(700)
                    print('CAPTURE SETTING',await page.evaluate('() => ({mic:state.settings.microphone_id,voice:state.voice,stream:Boolean(state.stream),toasts:document.querySelector(\"#toasts\").textContent})'),device,flush=True)
                    await page.wait_for_function('id => state.settings.microphone_id === id && state.voice && Boolean(state.stream)',arg=device)
                    assert await page.evaluate('() => state.stream.getAudioTracks().length') == 1
                    await page.locator('[data-page=chat]').click()
                    await page.locator('#wake-toggle').click()
                    await page.wait_for_function('() => !state.stream && !state.voice')
                    assert not errors,errors
                    print('PASS: status polling during capture startup, microphone change during voice, one capture, pause',flush=True)
                    (data/'settings-result.json').write_text(json.dumps({'passed':True,'human_microphone':False,'page_errors':errors}))
                    return
                await page.wait_for_function('() => state.wake.ready',timeout=30000)
            else:
                deadline = time.monotonic()+30
                while not native_ready.exists() or not (await client.get('/api/status')).json()['wake']['pid']:
                    if time.monotonic()>deadline: raise TimeoutError('Minimized native microphone did not start')
                    await asyncio.sleep(.3)
            root = psutil.Process(process.pid)
            before = {p.pid:sum(p.cpu_times()[:2]) for p in [root,*root.children(recursive=True)]}
            idle_started = time.monotonic()
            await asyncio.sleep(7)
            status = (await client.get('/api/status')).json()
            assert not status['engine']['loaded'] and not status['voice']['pid'],status
            processes = [root,*root.children(recursive=True)]
            cpu = sum(max(0,sum(p.cpu_times()[:2])-before.get(p.pid,sum(p.cpu_times()[:2]))) for p in processes)
            standby = {'tree_rss_mb':round(sum(p.memory_info().rss for p in processes)/1024**2),
                'host_cpu_percent':round(cpu/(time.monotonic()-idle_started)/psutil.cpu_count()*100,2),
                'whisper_loaded':False,'llm_loaded':False,'wake_worker_mb':round(psutil.Process(status['wake']['pid']).memory_info().rss/1024**2)}
            print('STANDBY',json.dumps(standby),flush=True)
            if args.split_pause and page:
                await page.wait_for_function('() => Boolean(state.pendingWakeChunks)',timeout=30000)
                held=(await client.get('/api/status')).json()
                assert not held['voice']['pid'] and not held['engine']['loaded'],held
                print('Standalone call held without loading Whisper or LLM',flush=True)
            recognized = answer = None
            deadline = time.monotonic()+150
            while not answer:
                if args.split_pause:
                    current=(await client.get('/api/status')).json()
                    if not current['settings']['wake_enabled'] and not current['wake']['pid']:
                        recognized='microfone pausado por voz';answer='Microfone pausado por voz';break
                rows = (await client.get('/api/conversations')).json()
                for row in rows:
                    chat = (await client.get('/api/conversations/'+row['id'])).json()
                    users = [m['content'] for m in chat['messages'] if m['role']=='user']
                    assistants = [m['content'] for m in chat['messages'] if m['role']=='assistant' and not m['interrupted']]
                    if users: recognized=users[0]
                    if assistants: answer=assistants[0]
                if time.monotonic()>deadline: raise TimeoutError('No voice response: '+str(recognized)+' '+str(await page.evaluate('() => ({voice:state.voice, processing:state.processing, recording:state.recording, samples:state.chunks.length, label:document.querySelector(\"#voice-state\").textContent, toasts:document.querySelector(\"#toasts\").textContent})') if page else {}))
                await asyncio.sleep(.5)
            assert ('microfone' if args.split_pause else 'horas') in recognized.casefold(), recognized
            if page:
                if not args.split_pause:
                    await page.wait_for_function('() => !state.voice && state.wake.ready && !state.processing',timeout=60000)
                    assert await page.evaluate('state.stream.getAudioTracks().length') == 1
                    await page.locator('#wake-toggle').click()
                await page.wait_for_function('() => !state.stream && !state.wake.ws && !state.settings.wake_enabled')
                await page.wait_for_timeout(4500)
                assert not await page.evaluate('Boolean(state.stream)')
                assert not (await client.get('/api/status')).json()['wake']['pid']
                assert not errors, errors
                await page.screenshot(path=str(data/'paused.png'))
            report = {'minimized_native':bool(args.exe),'standby':standby,'request_or_observed_action':recognized,
                'answer':answer,'human_microphone':False,'elapsed_seconds':round(time.monotonic()-started,1),
                'ui_pause_and_timeout':bool(page and not args.split_pause),'split_call_and_spoken_pause':args.split_pause,
                'page_errors':errors}
            (data/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=True),flush=True)
    finally:
        if browser: await browser.close()
        if client:
            try: await client.post('/api/shutdown')
            except httpx.HTTPError: pass
            await client.aclose()
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired: process.terminate();process.wait(10)


if __name__ == '__main__': asyncio.run(main())
