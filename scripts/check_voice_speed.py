"""Synthetic speech benchmarks and UI regression checks; no human capture or app launch."""
import argparse
import asyncio
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

import httpx
import numpy as np
import psutil
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pacoca.actions import explicit_action
from pacoca.native_voice import synthesize_female


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path)
    args=parser.parse_args()
    data=ROOT/'.test-data'/('voice-speed-frozen' if args.exe else 'voice-speed-dev')
    data.mkdir(exist_ok=True)
    (data/'settings.json').write_text(json.dumps({'onboarding_done':True,'wake_enabled':False,'updates_enabled':False,'idle_seconds':300}))
    connection=data/'connection.json';connection.unlink(missing_ok=True)
    env={**os.environ,'PACOCA_DATA':str(data),'PACOCA_ASSETS':str(ROOT/'assets'),'PYTHONPATH':str(ROOT/'src')}
    if args.exe:
        for key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):env.pop(key,None)
        windows=Path(os.environ.get('SystemRoot',r'C:\Windows'))
        env['PATH']=';'.join(map(str,(windows/'System32',windows,windows/'System32/WindowsPowerShell/v1.0')))
    command=[str(args.exe.resolve())] if args.exe else [sys.executable,str(ROOT/'run-pacoca.py')]
    process=subprocess.Popen(command+['--headless','--connection-file',str(connection)],env=env,cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    client=None;browser=None
    try:
        deadline=time.monotonic()+45
        while not connection.exists():
            if process.poll() is not None:raise RuntimeError('App startup failed')
            if time.monotonic()>deadline:raise TimeoutError('App startup')
            await asyncio.sleep(.2)
        c=json.loads(connection.read_text())
        client=httpx.AsyncClient(base_url=f"http://127.0.0.1:{c['port']}",headers={'X-Pacoca-Token':c['token']},trust_env=False,timeout=90)
        status=(await client.get('/api/status')).json()
        assert not status['engine']['loaded'] and not status['voice']['pid']
        assert status['voice']['female_available']
        wav=synthesize_female('Paçoca, abre o Spotify.',1)
        with wave.open(io.BytesIO(wav)) as w:
            pcm=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768
        pcm=np.concatenate([np.zeros(4000,dtype=np.float32),pcm,np.zeros(6400,dtype=np.float32)]).astype('<f4').tobytes()
        rows=[]
        for mode in ('fast','precise'):
            (await client.patch('/api/settings',json={'transcription_mode':mode})).raise_for_status()
            for i in range(2):
                response=await client.post('/api/transcribe',content=pcm,headers={'Content-Type':'application/octet-stream'})
                response.raise_for_status();result=response.json()
                action=explicit_action(result['text'])
                assert action and action['app']=='spotify' and action['action']=='open',result
                status=(await client.get('/api/status')).json()
                assert not status['engine']['loaded']
                row={'mode':mode,'cold_model':i==0,**result,'worker_rss_mb':round(psutil.Process(status['voice']['pid']).memory_info().rss/2**20)}
                rows.append(row);print(json.dumps(row,ensure_ascii=True),flush=True)
        (await client.patch('/api/settings',json={'transcription_mode':'fast'})).raise_for_status()
        started=time.monotonic()
        r=await client.post('/api/voice/preview',json={'voice_style':'female','voice_speed':1})
        assert r.status_code==200 and r.content[:4]==b'RIFF'
        female_ms=round((time.monotonic()-started)*1000)
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True,args=['--mute-audio'],executable_path=str(next((ROOT/'assets/browser').glob('chromium-*/chrome-win64/chrome.exe'))))
            page=await browser.new_page(viewport={'width':1320,'height':1000})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(c['url']);await page.wait_for_function('() => Boolean(state.status) && state.connected')
            await page.locator('[data-page=settings]').click()
            await page.wait_for_function('() => document.querySelector("#setting-idle").value === "300"')
            await page.locator('#setting-voice-style').select_option('female')
            await page.locator('#save-settings').click()
            await page.wait_for_function('() => state.settings.voice_style === "female"')
            await page.screenshot(path=str(data/'voice-settings.png'))
            await page.route('**/api/transcribe',lambda route:route.fulfill(json={'text':'','latency_ms':1}))
            await page.evaluate('''() => {
                state.voice=true;state.activeRun='test-in-progress';state.generating=true;
                state.recording=false;state.voiced=0;state.firstWakeUtterance=false;
                for(let i=0;i<4;i++)audioChunk(new Float32Array(512).fill(.1));
                if(state.activeRun!=='test-in-progress')throw Error('Noise cancelled the action');
                for(let i=0;i<16;i++)audioChunk(new Float32Array(512));
            }''')
            await page.wait_for_function('() => !state.processing')
            assert await page.evaluate('state.activeRun')=='test-in-progress'
            assert not errors,errors
            await page.evaluate('() => {state.voice=false;state.activeRun=null;state.generating=false;}')
        report={'frozen':bool(args.exe),'synthetic_audio':True,'human_microphone':False,'external_apps_launched':False,
                'llm_remained_asleep':True,'female_preview_ms':female_ms,'noise_does_not_cancel_action':True,'rows':rows}
        (data/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True),flush=True)
    finally:
        if browser:await browser.close()
        if client:
            try:await client.post('/api/shutdown')
            except httpx.HTTPError:pass
            await client.aclose()
        try:process.wait(timeout=30)
        except subprocess.TimeoutExpired:process.terminate();process.wait(10)


if __name__=='__main__':asyncio.run(main())
