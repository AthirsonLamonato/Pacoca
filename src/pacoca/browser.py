from __future__ import annotations

import ipaddress
import os
import socket
import uuid
from urllib.parse import urlparse

from .config import asset_root


class Browser:
    def __init__(self, settings):
        self.settings = settings
        self.driver = self.context = self.page = None
        self.observed = set()

    async def validate_url(self, url):
        import asyncio
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use um endereço http ou https sem credenciais.")
        host = parsed.hostname.casefold()
        allowed = self.settings.get("browser_domains", [])
        if allowed and not any(host==a or host.endswith("."+a) for a in allowed):
            raise PermissionError("Esse domínio não está autorizado nas configurações do navegador.")
        addresses = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or 443)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise PermissionError("O navegador da Paçoca não acessa serviços privados ou locais.")

    async def start(self):
        if self.context:
            return
        from playwright.async_api import async_playwright
        bundled = asset_root() / "browser"
        if bundled.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)
        self.driver = await async_playwright().start()
        self.context = await self.driver.chromium.launch_persistent_context(
            str(self.settings.directory / "Browser"), headless=False, accept_downloads=False,
            viewport={"width":1280,"height":900},service_workers="block")
        async def guard(route):
            if route.request.url.startswith(("data:","blob:")):
                return await route.continue_()
            try:
                await self.validate_url(route.request.url)
                await route.continue_()
            except (ValueError,PermissionError,OSError):
                await route.abort()
        await self.context.route("**/*", guard)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def inspect(self):
        if not self.page:
            raise RuntimeError("Abra uma página primeiro.")
        result = await self.page.evaluate("""prefix => {
            document.querySelectorAll('[data-pacoca-ref]').forEach(e=>e.removeAttribute('data-pacoca-ref'));
            const elements=[...document.querySelectorAll('a,button,input,textarea,select,[role=button]')]
                .filter(e=>e.getClientRects().length).slice(0,90).map((e,i)=>{
                const ref=prefix+'-'+String(i); e.setAttribute('data-pacoca-ref',ref);
                return {ref,tag:e.tagName,label:(e.getAttribute('aria-label')||e.innerText||e.placeholder||e.name||'').slice(0,120),type:e.type||''};});
            return {title:document.title,url:location.href,text:document.body.innerText.slice(0,10000),elements};
        }""",uuid.uuid4().hex[:8])
        self.observed = {e["ref"] for e in result["elements"]}
        return result

    async def action(self, action, url="", ref="", text="", index=0):
        if action == "close":
            await self.close()
            return {"verified":True,"message":"Navegador encerrado."}
        if action == "open":
            await self.validate_url(url)
            await self.start()
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return await self.inspect()
        if not self.context:
            raise RuntimeError("Abra uma página primeiro.")
        if action == "tabs":
            return {"tabs":[{"index":i,"url":p.url} for i,p in enumerate(self.context.pages)]}
        if action == "switch":
            if not 0 <= index < len(self.context.pages):
                raise ValueError("Aba não encontrada.")
            self.page = self.context.pages[index]
            await self.page.bring_to_front()
        elif action in ("click","fill","press"):
            if ref not in self.observed:
                raise ValueError("Consulte a página e use uma referência observada.")
            element = self.page.locator(f'[data-pacoca-ref="{ref}"]')
            if await element.count() != 1:
                raise ValueError("O elemento mudou. Consulte a página novamente.")
            if action == "click":
                await element.click(timeout=12000)
            elif action == "fill":
                await element.fill(text, timeout=12000)
            elif text in ("Enter","Tab","Escape","ArrowDown","ArrowUp"):
                await element.press(text)
            else:
                raise ValueError("Tecla não permitida.")
        elif action == "back":
            await self.page.go_back(wait_until="domcontentloaded")
        elif action != "inspect":
            raise ValueError("Ação de navegador inválida.")
        return await self.inspect()

    async def close(self):
        if self.context:
            await self.context.close()
        if self.driver:
            await self.driver.stop()
        self.context = self.driver = self.page = None
        self.observed.clear()
