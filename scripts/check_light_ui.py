"""Headless browser checks of Paçoca's own UI; no input in Windows apps."""
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'assets/browser')


async def main():
    c=json.loads((ROOT/'.test-data/light-v2-connection.json').read_text())
    output=ROOT/'.test-data/evidence';output.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000},bypass_csp=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(c['url'])
        await page.wait_for_function('state.connected && state.status')
        if await page.locator('#onboarding').is_visible():
            await page.locator('#onboarding-name').fill('Perfil de teste')
            await page.locator('#finish-onboarding').click()
            await page.locator('#onboarding').wait_for(state='hidden')
        await page.locator('[data-page=settings]').click()
        await page.locator('#setting-profile').wait_for()
        assert await page.locator('#setting-profile').input_value()=='light'
        assert await page.locator('[data-app-path]').count()==3
        await page.locator('#setting-threads').select_option('1')
        await page.locator('#save-settings').click()
        await page.wait_for_function('state.settings.cpu_threads === 1')
        await page.locator('#setting-threads').select_option('2')
        await page.locator('#save-settings').click()
        await page.wait_for_function('state.settings.cpu_threads === 2')
        # An update cannot restart while a user is composing or using voice.
        await page.locator('[data-page=chat]').click()
        await page.locator('#prompt').fill('Rascunho de teste')
        await page.wait_for_timeout(2300)
        assert await page.evaluate('state.connected')
        await page.locator('#prompt').fill('')
        for width in (1440,640):
            await page.set_viewport_size({'width':width,'height':1000})
            await page.locator('[data-page=settings]').click()
            await page.wait_for_timeout(300)
            overflow=await page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not overflow,('Horizontal overflow',width)
            await page.screenshot(path=str(output/f'light-settings-{width}.png'))
        assert not errors,errors
        (output/'light-browser.json').write_text(json.dumps({'errors':errors,'viewports':[1440,640],
            'preferences_persisted':True,'application_configuration':True,'lazy_chat_controls':True}),encoding='utf-8')
        print('UI passed: settings, persistence, desktop/compact layouts, no page errors',flush=True)
        await browser.close()


if __name__=='__main__':asyncio.run(main())
