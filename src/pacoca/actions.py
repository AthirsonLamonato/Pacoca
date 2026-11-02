"""Bounded desktop workflows for explicit application, game and music requests."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from . import windows
from .media import WindowsMedia,SpotifyUI,resolve_device
from .routing import normalized
from .screen import Screen,matching_lines

ALIASES={
    'valorant':('valorant',),
    'cs2':('cs','cs2','counter strike','counter-strike','counterstrike','counterstrike 2','counter strike 2','counter-strike 2'),
    'spotify':('spotify',),
}
PROCESSES={'valorant':{'valorant-win64-shipping.exe','valorant.exe'},'cs2':{'cs2.exe'},'spotify':{'spotify.exe'}}
_DLL_LOCK=threading.RLock()


def canonical_app(text):
    name=normalized(text).strip(' .!?')
    return next((key for key,aliases in ALIASES.items() if name in aliases),name)


def spawn_catalog_app(app):
    """Only catalog-sourced IDs reach the launcher; never a shell command string."""
    identifier=app['id']
    if re.fullmatch(r'steam://rungameid/\d{1,10}',identifier):
        command=[str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'explorer.exe'),identifier]
    elif Path(identifier).is_file() and Path(identifier).suffix.casefold()=='.exe':
        command=[identifier]
        if Path(identifier).name.casefold()=='riotclientservices.exe':
            command+=['--launch-product=valorant','--launch-patchline=live']
    elif identifier.startswith(('http://','https://')):
        raise ValueError('Esse item é um link da web. Escolha o aplicativo instalado.')
    else:command=[str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'explorer.exe'),'shell:AppsFolder\\'+identifier]
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with _DLL_LOCK:
        kernel=ctypes.windll.kernel32 if os.name=='nt' else None
        if kernel:
            kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p];kernel.SetDllDirectoryW(None)
        try:subprocess.Popen(command,creationflags=flags)
        finally:
            if kernel and getattr(sys,'frozen',False):kernel.SetDllDirectoryW(str(sys._MEIPASS))


def explicit_action(text):
    """Fast path only for a complete explicit request; questions/examples fall through."""
    value=text.strip().rstrip('.!?').strip()
    value=re.sub(r'(?i)^paçoca[,! ]+','',value)
    value=re.sub(r'(?i)\s*,?\s*por favor$','',value)
    n=normalized(value)
    prefix=r'(?:(?:pode|poderia|consegue)\s+)?(?:abre|abra|abrir|inicia|inicie|iniciar)\s+(?:(?:os?|as?)\s+)?'
    if re.match(prefix,n):
        tail=re.sub(prefix,'',n,count=1)
        if re.match(r'^(?:cs2?|counter[ -]strike(?: 2)?)\b',tail) and re.fullmatch(r'(?:cs2?|counter[ -]strike(?: 2)?)(?:\s+e\s+(?:abre|abra|abrir|entra|entre|entrar|inicia|inicie|iniciar|joga|jogue|jogar))?\s+(?:(?:o|no|um)\s+)?(?:mata[ -]?mata|deathmatch)',tail):
            return {'action':'deathmatch','app':'cs2','query':'','device':''}
        if tail.startswith('spotify'):
            play=re.search(r'(?i)\b(?:toca|toque|tocar|reproduz|reproduza)\s+(.+)',value)
            if play:return parse_music(play.group(1))
            if re.fullmatch(r'spotify(?: no (?:pc|computador))?',tail):
                return {'action':'open','app':'spotify','query':'','device':''}
            return None
        if re.search(r'\b(e|mas|depois|entao)\b',tail):return None
        tail=re.sub(r'\s+(no pc|no computador|pra mim|para mim)$','',tail).strip()
        if 0<len(tail)<=80:return {'action':'open','app':canonical_app(tail),'query':'','device':''}
    play=re.fullmatch(r'(?i)(?:pode\s+)?(?:toca|toque|tocar|reproduza|reproduz|quero ouvir)\s+(.+)',value)
    if play:return parse_music(play.group(1))
    move=re.fullmatch(r'(?i)(?:(?:agora\s+)?(?:passa|passe|transfere|transfira|manda|mande|continua|continue))\s+(?:(?:a musica|a música|isso)\s+)?(?:pra|pro|para|na|no)\s+(?:a\s+|o\s+)?(.+)',value)
    if move and 'mensag' not in n:
        return {'action':'transfer','app':'spotify','query':'','device':move.group(1).strip()}
    simple={'pausa':'pause','pause':'pause','pausa a musica':'pause','pause a musica':'pause',
            'continua a musica':'resume','continue a musica':'resume','continua o spotify':'resume',
            'proxima musica':'next','proxima faixa':'next','volta a musica anterior':'previous',
            'quais dispositivos do spotify estao disponiveis':'devices'}
    if n in simple:return {'action':simple[n],'app':'spotify','query':'','device':''}
    return None


def parse_music(value):
    match=re.fullmatch(r'(?i)(.+?)\s+(?:na|no|em|pra|pro|para)\s+(?:a\s+|o\s+)?(alexa(?: .*)?|echo(?: .*)?|celular|telefone|pc|computador|iphone(?: .*)?|galaxy(?: .*)?)',value.strip())
    query,device=(match.group(1),match.group(2)) if match else (value,'')
    query=re.sub(r'(?i)^(?:a\s+)?(?:música|musica|faixa)\s+','',query).strip()
    if normalized(query) in ('musica','a musica','uma musica','aqui','no spotify'):
        query=''
    return {'action':'play' if query else 'resume','app':'spotify','query':query[:300],'device':device[:120]}


def track_matches(query,state):
    if not query:return True
    terms={w for w in normalized(query).split() if len(w)>1 and w not in {'de','do','da','por','the','musica','faixa'}}
    observed=normalized(state.get('title','')+' '+state.get('artist',''))
    return bool(terms) and sum(word in observed for word in terms)/len(terms)>=.8


class ApplicationCatalog:
    def __init__(self,settings):
        self.settings=settings;self.cached=[];self.checked=0

    def entries(self,refresh=False):
        if refresh or time.monotonic()-self.checked>600:
            self.cached=windows.applications();self.checked=time.monotonic()
        return list(self.cached)

    def resolve(self,query):
        key=canonical_app(query)
        path=self.settings.get('application_paths',{}).get(key)
        if path:
            target=Path(path).resolve()
            if target.is_file() and target.suffix.casefold()=='.exe':return {'id':str(target),'name':key,'key':key}
        aliases={normalized(a) for a in ALIASES.get(key,(query,))}
        entries=self.entries()
        matches=[a for a in entries if normalized(a['name']) in aliases or a['id'].casefold()==query.casefold()]
        if not matches:matches=[a for a in entries if any(q in normalized(a['name']) for q in aliases)]
        if len(matches)!=1:
            raise RuntimeError('Não encontrei um aplicativo único para '+query+'. '+
                ('Encontrei: '+', '.join(a['name'] for a in matches[:6]) if matches else 'Confira se ele está instalado ou escolha o executável em Configurações.'))
        return {**matches[0],'key':key}

    def window(self,app):
        candidates=windows.windows()
        expected=PROCESSES.get(app['key'])
        if expected:
            matches=[w for w in candidates if w['process'].casefold() in expected]
        else:
            words=[w for w in normalized(app['name']).split() if len(w)>3]
            matches=[w for w in candidates if words and all(p in normalized(w['title']) for p in words)]
        return matches[0] if len(matches)==1 else next((w for w in matches if normalized(app['name']) in normalized(w['title'])),None)

    async def open(self,query,cancel,emit):
        key=canonical_app(query)
        app={'name':{'spotify':'Spotify','cs2':'Counter-Strike 2','valorant':'Valorant'}.get(key,key),'key':key}
        window=await asyncio.to_thread(self.window,app) if key in PROCESSES else None
        if window is None:
            app=await asyncio.to_thread(self.resolve,query)
            window=await asyncio.to_thread(self.window,app)
        if window is None:
            await asyncio.to_thread(spawn_catalog_app,app)
            deadline=time.monotonic()+90
            await emit('Aguardando '+app['name']+' abrir')
            while window is None:
                if cancel.is_set():raise asyncio.CancelledError
                if time.monotonic()>deadline:
                    return {'verified':False,'state':'launching','app':app['name'],
                        'message':'Pedi a abertura de '+app['name']+', mas a janela do aplicativo ainda não foi confirmada. Confira o launcher.'}
                await asyncio.sleep(.5)
                window=await asyncio.to_thread(self.window,app)
        focused=True
        try:await asyncio.to_thread(windows.focus_window,window['id'])
        except Exception:focused=False
        return {'verified':True,'state':'ready','app':app['name'],'window':window,'focused':focused,
            'message':app['name']+' está aberto.'+('' if focused else ' O Windows não permitiu trazer a janela para frente.')}


class DesktopActions:
    def __init__(self,settings,runtime,*,catalog=None,media=None,spotify_ui=None,screen=None):
        self.settings,self.runtime=settings,runtime
        self.catalog=catalog or ApplicationCatalog(settings)
        self.media=media or WindowsMedia();self.spotify=spotify_ui or SpotifyUI();self.screen=screen or Screen()
        self.lock=asyncio.Lock()
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pacoca-desktop')

    async def ui(self,function,*args):
        return await asyncio.get_running_loop().run_in_executor(self.executor,lambda:function(*args))

    async def execute(self,args,progress):
        args=args.model_copy(update={'app':canonical_app(args.app)})
        cancel=threading.Event()
        async with self.lock:
            try:
                if args.action=='deathmatch' and args.app!='cs2':raise ValueError('Mata-mata está disponível no CS2.')
                if args.action not in ('open','deathmatch') and args.app!='spotify':raise ValueError('Os controles de música são exclusivos do Spotify.')
                if args.app in ('cs2','valorant'):
                    await self.runtime.stop_process()
                if args.action=='open':return await self.catalog.open(args.app,cancel,progress)
                if args.action=='deathmatch':return await self.deathmatch(cancel,progress)
                return await self.music(args,cancel,progress)
            except asyncio.CancelledError:
                cancel.set();raise
            except (OSError,RuntimeError,ValueError) as exc:
                return {'verified':False,'state':'needs_input','message':str(exc)[:500]}

    async def deathmatch(self,cancel,progress):
        opened=await self.catalog.open('cs2',cancel,progress)
        if not opened['verified']:return opened
        if not opened['focused']:return {**opened,'verified':False,'message':'Abra a janela do CS2 para eu conferir o menu do mata-mata.'}
        hwnd=opened['window']['id']
        await progress('Conferindo o menu do CS2')
        options=play=[]
        for _ in range(40):
            observed=await self.screen.observe(hwnd,cancel)
            options=matching_lines(observed,['MATA-MATA','MATA MATA','DEATHMATCH'])
            play=matching_lines(observed,['JOGAR','PLAY'],upper=.45)
            if options or play:break
            await asyncio.sleep(.75)
        if not options:
            if len(play)!=1:
                return {'verified':False,'state':'needs_input','message':'Não confirmei o menu principal do CS2. Se estiver em uma partida, não vou sair dela automaticamente.'}
            await self.screen.click(hwnd,observed,play[0],cancel)
            await asyncio.sleep(.8)
            observed=await self.screen.observe(hwnd,cancel)
        official=matching_lines(observed,['CRIAÇÃO DE PARTIDAS','CRIACAO DE PARTIDAS','MATCHMAKING','OFFICIAL MATCHMAKING'],upper=.5)
        if len(official)!=1:
            return {'verified':False,'state':'needs_input','message':'Não confirmei a aba de criação de partidas online. Confira o menu Jogar do CS2; não vou iniciar uma sessão de treino no lugar do mata-mata online.'}
        await self.screen.click(hwnd,observed,official[0],cancel)
        await asyncio.sleep(.5)
        for _ in range(12):
            observed=await self.screen.observe(hwnd,cancel)
            options=matching_lines(observed,['MATA-MATA','MATA MATA','DEATHMATCH'])
            if options:break
            await asyncio.sleep(.6)
        if not options:return {'verified':False,'state':'needs_input','message':'O menu abriu, mas não localizei Mata-mata nesta versão da interface.'}
        if len(options)>1:
            return {'verified':False,'state':'needs_input','message':'Encontrei mais de uma opção de Mata-mata. Confira o menu para eu não escolher a errada.'}
        await progress('Selecionando Mata-mata')
        await self.screen.click(hwnd,observed,options[0],cancel)
        await asyncio.sleep(.7)
        observed=await self.screen.observe(hwnd,cancel)
        text=normalized(' '.join(line['text'] for line in observed['lines']))
        if not any(word in text for word in ('mata-mata','mata mata','deathmatch')):
            return {'verified':False,'state':'needs_input','message':'A seleção do modo não pôde ser conferida. Parei antes de iniciar uma busca.'}
        play=matching_lines(observed,['JOGAR','INICIAR','GO','PLAY'],lower=.55)
        if len(play)!=1:
            return {'verified':False,'state':'mode_selected','message':'Selecionei Mata-mata, mas não identifiquei um botão único para iniciar. Confira o menu do jogo.'}
        await self.screen.click(hwnd,observed,play[0],cancel)
        for _ in range(12):
            await asyncio.sleep(.5)
            observed=await self.screen.observe(hwnd,cancel)
            text=normalized(' '.join(line['text'] for line in observed['lines']))
            if any(word in text for word in ('buscando partida','buscando uma partida','procurando partida','searching for','cancelar busca')):
                return {'verified':True,'state':'searching','mode':'deathmatch','message':'A busca de partida do Mata-mata foi iniciada no CS2.'}
        return {'verified':False,'state':'requested','message':'O início foi solicitado, mas não confirmei o estado da busca. Confira o CS2; não vou repetir o clique.'}

    async def music(self,args,cancel,progress):
        if args.action in ('pause','resume','next','previous') and not args.device:
            before=await self.media.state() if args.action in ('next','previous') else None
            state=await self.media.command(args.action)
            if before:
                for _ in range(12):
                    if (state['title'],state['artist'])!=(before['title'],before['artist']):break
                    if cancel.is_set():raise asyncio.CancelledError
                    await asyncio.sleep(.25)
                    state=await self.media.state()
            verified=not before or (state['title'],state['artist'])!=(before['title'],before['artist'])
            return {'verified':verified,'state':state['status'],'track':state,
                    'message':('Spotify: '+state['title']+' — '+state['artist'] if verified else 'O controle foi enviado, mas a mudança de faixa ainda não foi confirmada.')}
        opened=await self.catalog.open('spotify',cancel,progress)
        if not opened['verified']:return opened
        hwnd=opened['window']['id']
        if not opened['focused']:return {'verified':False,'state':'needs_input','message':'Traga o Spotify para frente para conferir esse pedido.'}
        if args.action=='status':return {'verified':True,'state':'observed','track':await self.media.state(),'message':'Consultei a reprodução atual do Spotify.'}
        if args.query:
            await progress('Buscando '+args.query+' no Spotify')
            for attempt in range(20):
                try:
                    if await self.ui(self.spotify.search,hwnd,args.query):break
                except RuntimeError:
                    if attempt==19:raise
                await asyncio.sleep(.4)
            matches=[]
            for _ in range(12):
                if cancel.is_set():raise asyncio.CancelledError
                await asyncio.sleep(.4)
                matches=await self.ui(self.spotify.tracks,hwnd,args.query)
                if matches:break
            unique={m['label']:m for m in matches}
            if len(unique)!=1:
                return {'verified':False,'state':'needs_input','candidates':list(unique)[:6],
                    'message':'Encontrei mais de uma faixa. Diga o artista ou o nome completo.' if unique else 'Não localizei uma faixa única nessa busca do Spotify. Diga também o artista.'}
            await self.ui(self.spotify.play_track,hwnd,next(iter(unique)))
        if args.device or args.action=='devices':
            await progress('Conferindo os dispositivos do Spotify')
            await self.ensure_picker(hwnd,cancel)
            devices=[];observation=None
            for _ in range(8):
                await asyncio.sleep(.3)
                devices,observation=await self.observe_devices(hwnd,cancel,args.device)
                if devices:break
            if args.action=='devices':
                return {'verified':True,'state':'observed','devices':devices,
                        'message':'Dispositivos encontrados: '+', '.join(d['label'] for d in devices) if devices else 'Não encontrei dispositivos disponíveis nessa lista.'}
            chosen=resolve_device(devices,args.device,self.settings.get('spotify_device',''))
            if not chosen:
                return {'verified':False,'state':'needs_input','devices':devices,
                    'message':'Não encontrei um dispositivo único para '+args.device+'. '+
                    ('Diga o nome exato: '+', '.join(d['label'] for d in devices) if devices else 'Abra o Spotify no celular ou confira se a Alexa está disponível no Spotify Connect.')}
            # Re-observe the exact device label before clicking its visible row.
            devices,observation=await self.observe_devices(hwnd,cancel,args.device)
            chosen=next((d for d in devices if d['label']==chosen['label']),None)
            if not chosen:raise RuntimeError('A lista de dispositivos mudou. Peça novamente pelo nome do dispositivo.')
            if not chosen['selected']:
                await self.screen.click(hwnd,observation,chosen['line'],cancel)
            await asyncio.sleep(.6)
            if args.action in ('play','resume') and not args.query:await self.media.command('resume')
            await self.ensure_picker(hwnd,cancel)
            selected_ok=False;state={'title':'','artist':'','status':'unknown'}
            for _ in range(16):
                if cancel.is_set():raise asyncio.CancelledError
                selected,_=await self.observe_devices(hwnd,cancel,args.device)
                selected_ok=any(d['label']==chosen['label'] and d['selected'] for d in selected)
                try:state=await self.media.state()
                except RuntimeError:pass
                if selected_ok and (args.action=='transfer' or state['status']=='playing' and track_matches(args.query,state)):break
                await asyncio.sleep(.35)
            verified=selected_ok and (args.action=='transfer' or state['status']=='playing' and track_matches(args.query,state))
            if selected_ok:self.settings.update({'spotify_device':chosen['label']})
            return {'verified':verified,'state':'playing' if verified and state['status']=='playing' else 'requested',
                'device':chosen['label'],'track':state,
                'message':('O Spotify indica '+state['title']+' em '+chosen['label']+'.') if verified else
                'A troca para '+chosen['label']+' foi solicitada, mas a seleção não foi confirmada. Confira o seletor do Spotify.'}
        if args.action in ('play','resume') and not args.query:await self.media.command('resume')
        for _ in range(24):
            if cancel.is_set():raise asyncio.CancelledError
            await asyncio.sleep(.3)
            try:state=await self.media.state()
            except RuntimeError:continue
            if state['status']=='playing' and state['title'] and track_matches(args.query,state):
                return {'verified':True,'state':'playing','track':state,'message':'Tocando '+state['title']+' — '+state['artist']+' no Spotify.'}
        return {'verified':False,'state':'requested','message':'O pedido foi enviado ao Spotify, mas não confirmei a reprodução.'}

    def close(self):self.executor.shutdown(wait=False,cancel_futures=True)

    async def ensure_picker(self,hwnd,cancel):
        observed=await self.screen.observe(hwnd,cancel)
        if any(normalized(line['text']).strip()=='connect' for line in observed['lines']):return
        await self.ui(self.spotify.device_picker,hwnd)
        await asyncio.sleep(.4)

    async def observe_devices(self,hwnd,cancel,target=''):
        observation=await self.screen.observe(hwnd,cancel)
        devices=[]
        for line in observation['lines']:
            label=line['text'];name=normalized(label).strip()
            if name.startswith(('mais opcoes','conectar','nenhum','nao consegue','iniciar','ouca')):continue
            if any(word in name for word in ('echo','alexa','iphone','galaxy','android','celular','este computador','this computer','este pc')) or target and normalized(target)==name:
                devices.append({'label':label,'selected':bool(line.get('selected_green')),'line':line})
        return devices,observation
