"""Exercise the running application with real inference and a browser UI."""
import asyncio
import json
import os
from pathlib import Path
import time

import httpx
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'assets'/'browser')


async def main():
    connection=json.loads((ROOT/os.getenv('PACOCA_CONNECTION','.test-data/connection.json')).read_text())
    base=f"http://127.0.0.1:{connection['port']}"
    output=ROOT/'.test-data/evidence'
    output.mkdir(parents=True,exist_ok=True)
    async with httpx.AsyncClient(base_url=base,headers={'X-Pacoca-Token':connection['token']},timeout=120,trust_env=False) as client:
        results=[]
        for prompt in ['Oi! Quem é você e onde as minhas conversas ficam?',
                       'Consulte as informações reais do meu computador e me diga quanta memória RAM ele tem.',
                       'Meu projeto favorito se chama Aurora. Não guarde na memória ainda, só estamos conversando.',
                       'Como se chama meu projeto favorito?']:
            if not results:
                cid=(await client.post('/api/conversations')).json()['id']
            t=time.monotonic()
            response=await client.post('/api/chat',json={'conversation_id':cid,'text':prompt,'voice':False})
            response.raise_for_status()
            id=response.json()['run_id']
            while True:
                task=(await client.get('/api/tasks/'+id)).json()
                if task['status'] not in ('running','waiting_approval'):
                    break
                if time.monotonic()-t>160:
                    raise TimeoutError(task)
                await asyncio.sleep(.3)
            result={'prompt':prompt,'seconds':round(time.monotonic()-t,2),'status':task['status'],'answer':task['output'],
                    'tools':[e['data']['name'] for e in task['events'] if e['kind']=='tool']}
            results.append(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
        (output/'conversation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(connection['url'])
        await page.wait_for_function("document.querySelector('#profile-name').textContent !== 'Seu espaço pessoal' || document.querySelector('#onboarding').open")
        if await page.locator('#onboarding').is_visible():
            await page.locator('#onboarding-name').fill('Athy')
            await page.locator('#finish-onboarding').click()
            await page.locator('#onboarding').wait_for(state='hidden')
        await page.screenshot(path=str(output/'home.png'),full_page=True)
        await page.locator('[data-page=memory]').click()
        await page.locator('#add-memory').click()
        await page.locator('.modal-input').fill('Esta é uma lembrança de teste da interface.')
        await page.get_by_role('button',name='Guardar memória',exact=True).click()
        await page.locator('.memory-card').wait_for()
        await page.screenshot(path=str(output/'memory.png'),full_page=True)
        await page.locator('[data-page=settings]').click()
        await page.screenshot(path=str(output/'settings.png'),full_page=True)
        await page.locator('[data-page=chat]').click()
        await page.locator('#prompt').fill('Me dê uma ideia curta para começar um projeto de IA local.')
        await page.locator('#send').click()
        await page.locator('.message.assistant .message-tools').last.wait_for(timeout=120000)
        await page.screenshot(path=str(output/'conversation.png'),full_page=True)
        await page.set_viewport_size({'width':640,'height':900})
        await page.locator('#new-chat').click()
        await page.screenshot(path=str(output/'compact.png'),full_page=True)
        assert not errors,errors
        (output/'browser.json').write_text(json.dumps({'page_errors':errors,'screenshots':5},indent=2))
        await browser.close()


if __name__=='__main__':
    asyncio.run(main())
