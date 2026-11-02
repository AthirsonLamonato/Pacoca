"""Real local voice pipeline and synthetic microphone test; never records a person."""
import asyncio
import io
import json
import os
from pathlib import Path
import time
import wave

import httpx
import websockets
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'assets/browser')


async def main():
    c=json.loads((ROOT/os.getenv('PACOCA_CONNECTION','.test-data/cuda-connection.json')).read_text())
    base='http://127.0.0.1:'+str(c['port'])
    evidence=ROOT/'.test-data/evidence';evidence.mkdir(exist_ok=True,parents=True)
    async with httpx.AsyncClient(base_url=base,headers={'X-Pacoca-Token':c['token']},timeout=120,trust_env=False) as client:
        cid=(await client.post('/api/conversations')).json()['id']
        async with websockets.connect(f"ws://127.0.0.1:{c['port']}/events?token={c['token']}") as ws:
            await ws.recv()
            start=time.monotonic()
            run=(await client.post('/api/chat',json={'conversation_id':cid,'text':'Diga apenas uma frase curta de boas-vindas.','voice':True})).json()['run_id']
            first_token=first_audio=None
            wavs=[]
            while True:
                event=json.loads(await asyncio.wait_for(ws.recv(),90))
                if event.get('run_id')!=run:continue
                if event['type']=='token' and first_token is None:first_token=time.monotonic()-start
                if event['type']=='audio':
                    if first_audio is None:first_audio=time.monotonic()-start
                    import base64
                    wavs.append(base64.b64decode(event['audio']))
                if event['type']=='error':raise RuntimeError(event)
                if event['type']=='done':break
            assert wavs,'No local speech was emitted'
            (evidence/'local-voice.wav').write_bytes(wavs[0])
        # A generated greeting supplies input to Chromium's fake microphone.
        generated=await client.post('/api/voice/preview')
        generated.raise_for_status()
        with wave.open(io.BytesIO(generated.content)) as w:
            rate=w.getframerate();frames=w.readframes(w.getnframes());channels=w.getnchannels()
        fake=evidence/'synthetic-microphone.wav'
        with wave.open(str(fake),'wb') as out:
            out.setnchannels(channels);out.setsampwidth(2);out.setframerate(rate)
            out.writeframes(b'\0'*(rate*channels)+frames+b'\0'*(rate*channels*2*4))
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
            '--use-file-for-fake-audio-capture='+str(fake),'--mute-audio'])
        page=await browser.new_page(viewport={'width':1320,'height':900},permissions=['microphone'])
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(c['url'])
        await page.wait_for_function("document.querySelector('#engine-label').textContent.includes('Local')")
        await page.locator('#new-chat').click()
        await page.locator('#start-voice').click()
        await page.locator('#voice-session').wait_for()
        await page.locator('.message.user').wait_for(timeout=90000)
        recognized=await page.locator('.message.user .message-content').first.inner_text()
        assert 'paçoca' in recognized.casefold(),recognized
        await page.locator('.message.assistant .message-tools').first.wait_for(timeout=90000)
        await page.locator('#end-voice').click()
        await page.screenshot(path=str(evidence/'voice-conversation.png'))
        assert not await page.evaluate('state.voice')
        # Stale response/audio is ignored after an explicit interruption.
        await page.locator('#prompt').fill('Escreva uma história longa sobre uma viagem pelo universo.')
        await page.locator('#send').click()
        await page.locator('#activity').wait_for()
        await page.locator('#stop-response').click()
        await page.wait_for_timeout(400)
        assert await page.locator('#activity').is_hidden()
        assert not errors,errors
        await browser.close()
    result={'first_token_seconds':round(first_token,2),'first_audio_seconds':round(first_audio,2),'audio_chunks':len(wavs),
            'synthetic_microphone_transcript':recognized,'human_microphone_used':False,'page_errors':errors}
    (evidence/'voice-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)


if __name__=='__main__':asyncio.run(main())
