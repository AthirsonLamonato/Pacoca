import asyncio
from types import SimpleNamespace

import pytest

from pacoca.actions import DesktopActions,explicit_action,ApplicationCatalog,track_matches
from pacoca.config import Settings
from pacoca.media import resolve_device
from pacoca.screen import matching_lines
from pacoca.tools import ComputerAction,ToolRegistry
from pacoca.store import Store
from pacoca.browser import Browser
from pacoca.conversation import Conversations
from test_core import FakeRuntime


@pytest.mark.parametrize('text,action,app',[
    ('Abre o Valorant','open','valorant'),('Pode abrir o Spotify no PC?','open','spotify'),
    ('Paçoca, abre os Spotify.','open','spotify'),
    ('abre o cs e abre o mata mata','deathmatch','cs2'),
    ('Abre o CS e entra no mata-mata','deathmatch','cs2'),
    ('Abre o Counter-Strike 2 e iniciar o deathmatch','deathmatch','cs2'),
    ('Toca Numb Linkin Park na Alexa','play','spotify'),
    ('abre o spotify no pc, mas tocar Numb no celular','play','spotify'),
    ('Agora transfere a música para a Alexa','transfer','spotify'),
    ('Próxima música','next','spotify'),
])
def test_explicit_requests(text,action,app):
    result=explicit_action(text)
    assert result and result['action']==action and result['app']==app


@pytest.mark.parametrize('text',[
    'Não abra o Valorant','Como eu abriria o CS e o mata-mata?',
    'Por exemplo, abre o Spotify','Se eu disser abre o Valorant, o que acontece?',
    'Abra os discos e depois mata-mata','Abra o Spotify e apague os arquivos',
    'Mande mensagem para João','Gostaria de conversar sobre abrir o CS',
])
def test_conversation_and_compound_requests_do_not_trigger_fast_actions(text):
    assert explicit_action(text) is None


def test_music_keeps_exact_song_and_requested_output():
    assert explicit_action('toca Numb Linkin Park na Alexa')['query']=='Numb Linkin Park'
    assert explicit_action('toca Numb Linkin Park no celular')['device']=='celular'
    assert explicit_action('toca Numb Linkin Park')['device']==''


def test_device_ambiguity_does_not_pick_first():
    devices=[{'label':'Echo da sala'},{'label':'Echo do quarto'},{'label':'Este computador'}]
    assert resolve_device(devices,'alexa') is None
    assert resolve_device(devices,'alexa','Echo do quarto')==devices[1]
    assert resolve_device(devices,'pc')==devices[2]
    assert resolve_device(devices,'celular') is None


def test_catalog_does_not_guess_between_installed_apps(tmp_path):
    catalog=ApplicationCatalog(Settings(tmp_path))
    catalog.entries=lambda:[{'name':'Steam','id':'steam.exe'},{'name':'Steam Support','id':'https://help.steampowered.com'}]
    assert catalog.resolve('Steam')['id']=='steam.exe'
    with pytest.raises(RuntimeError):catalog.resolve('Stea')


@pytest.mark.asyncio
async def test_known_running_app_does_not_enumerate_start_menu(tmp_path,monkeypatch):
    catalog=ApplicationCatalog(Settings(tmp_path))
    monkeypatch.setattr('pacoca.actions.windows.windows',lambda:[{'id':123,'title':'Spotify','process':'Spotify.exe'}])
    monkeypatch.setattr('pacoca.actions.windows.focus_window',lambda hwnd:None)
    def expensive():raise AssertionError('Start menu must not be consulted for an already open app')
    monkeypatch.setattr('pacoca.actions.windows.applications',expensive)
    result=await catalog.open('spotify',__import__('threading').Event(),async_noop)
    assert result['verified'] and result['focused'] and result['app']=='Spotify'


@pytest.mark.asyncio
async def test_direct_action_does_not_call_model_or_ask_per_click(tmp_path):
    settings=Settings(tmp_path);store=Store(tmp_path/'test.db');runtime=FakeRuntime()
    class Actions:
        async def execute(self,args,progress):
            await progress('Conferindo a janela')
            return {'verified':True,'message':'Valorant está aberto.'}
    tools=ToolRegistry(settings,store,Browser(settings),Actions())
    conversations=Conversations(settings,store,runtime,tools,None)
    rid=await conversations.submit(store.conversation()['id'],'Abre o Valorant')
    await conversations.runs[rid].task
    assert not runtime.inputs and not conversations.approvals
    task=store.query('SELECT * FROM tasks WHERE id=?',(rid,))[0]
    assert task['status']=='completed' and task['output']=='Valorant está aberto.'
    store.close()


@pytest.mark.asyncio
async def test_action_result_remains_unverified(tmp_path):
    settings=Settings(tmp_path);store=Store(tmp_path/'test.db');runtime=FakeRuntime()
    class Actions:
        async def execute(self,args,progress):return {'verified':False,'message':'Confira o launcher.'}
    tools=ToolRegistry(settings,store,Browser(settings),Actions())
    conversations=Conversations(settings,store,runtime,tools,None)
    rid=await conversations.submit(store.conversation()['id'],'Abre o Valorant')
    await conversations.runs[rid].task
    assert store.query('SELECT status FROM tasks WHERE id=?',(rid,))[0]['status']=='unverified'
    assert not runtime.inputs
    store.close()


@pytest.mark.asyncio
async def test_only_spotify_media_is_used_and_next_is_verified(tmp_path):
    class Media:
        async def state(self):return {'title':'Nova','artist':'Artista','status':'playing'}
        async def command(self,action):return {'title':'Nova','artist':'Artista','status':'playing'}
    controller=DesktopActions(Settings(tmp_path),FakeRuntime(),media=Media())
    result=await controller.execute(ComputerAction(action='pause',app='spotify'),async_noop)
    assert result['verified'] and result['track']['title']=='Nova'
    rejected=await controller.execute(ComputerAction(action='play',app='brave'),async_noop)
    assert not rejected['verified']
    controller.close()


async def async_noop(_):pass


@pytest.mark.asyncio
async def test_deathmatch_stops_without_observed_menu(tmp_path,monkeypatch):
    import pacoca.actions as module
    async def instant(_):pass
    monkeypatch.setattr(module.asyncio,'sleep',instant)
    class Catalog:
        async def open(self,*args):return {'verified':True,'focused':True,'window':{'id':1}}
    class Screen:
        async def observe(self,*args):return {'lines':[{'text':'PARTIDA EM ANDAMENTO','rect':(0,10,120,25)}],'geometry':{'height':900,'scale':1}}
        async def click(self,*args):pytest.fail('No observed target: must not click')
    controller=DesktopActions(Settings(tmp_path),FakeRuntime(),catalog=Catalog(),screen=Screen())
    result=await controller.execute(ComputerAction(action='deathmatch',app='cs2'),async_noop)
    assert not result['verified'] and result['state']=='needs_input'
    controller.close()


def test_old_or_unrelated_track_is_not_reported_as_requested_song():
    assert track_matches('Numb do Linkin Park',{'title':'Numb','artist':'Linkin Park'})
    assert not track_matches('Numb Linkin Park',{'title':'Outra faixa','artist':'Outro artista'})


@pytest.mark.asyncio
async def test_native_media_does_not_control_browser_session(monkeypatch):
    import winrt.windows.media.control as module
    from pacoca.media import WindowsMedia
    spotify=SimpleNamespace(source_app_user_model_id='Spotify.exe')
    brave=SimpleNamespace(source_app_user_model_id='Brave')
    class Manager:
        @staticmethod
        async def request_async():return SimpleNamespace(get_sessions=lambda:[brave,spotify])
    monkeypatch.setattr(module,'GlobalSystemMediaTransportControlsSessionManager',Manager)
    assert await WindowsMedia().session() is spotify
    class OnlyBrowser:
        @staticmethod
        async def request_async():return SimpleNamespace(get_sessions=lambda:[brave])
    monkeypatch.setattr(module,'GlobalSystemMediaTransportControlsSessionManager',OnlyBrowser)
    with pytest.raises(RuntimeError):await WindowsMedia().session()


@pytest.mark.asyncio
@pytest.mark.parametrize('ambiguous',[False,True])
async def test_connect_selects_observed_device_and_checks_selection(tmp_path,ambiguous):
    clicked=[]
    class Catalog:
        async def open(self,*args):return {'verified':True,'focused':True,'window':{'id':1}}
    class UI:
        def device_picker(self,*args):pass
    class Media:
        async def state(self):return {'title':'Numb','artist':'Linkin Park','status':'playing'}
    class Screen:
        async def observe(self,*args):
            def line(text,selected=False):return {'text':text,'rect':(20,20,100,40),'selected_green':selected}
            return {'lines':[line('Connect'),line('Este computador',not clicked),line('Echo da sala',bool(clicked)),*([line('Echo do quarto')] if ambiguous else [])]}
        async def click(self,hwnd,observed,line,cancel):clicked.append(line['text'])
    controller=DesktopActions(Settings(tmp_path),FakeRuntime(),catalog=Catalog(),spotify_ui=UI(),media=Media(),screen=Screen())
    result=await controller.execute(ComputerAction(action='transfer',app='spotify',device='alexa'),async_noop)
    assert result['verified'] is (not ambiguous)
    assert clicked==([] if ambiguous else ['Echo da sala'])
    controller.close()


@pytest.mark.asyncio
async def test_game_workflow_selects_online_deathmatch_and_verifies_search(tmp_path,monkeypatch):
    import pacoca.actions as module
    async def instant(_):pass
    monkeypatch.setattr(module.asyncio,'sleep',instant)
    clicked=[]
    def frame(*labels):return {'geometry':{'height':900,'scale':1},'lines':[
        {'text':label,'rect':(10,y,140,y+25)} for label,y in labels]}
    menu=frame(('CRIAÇÃO DE PARTIDAS',100),('MATA-MATA',200))
    frames=iter([frame(),frame(('JOGAR',50)),menu,menu,frame(('MATA-MATA',200),('JOGAR',800)),frame(('BUSCANDO PARTIDA',800))])
    class Catalog:
        async def open(self,*args):return {'verified':True,'focused':True,'window':{'id':1}}
    class Screen:
        async def observe(self,*args):return next(frames)
        async def click(self,hwnd,observation,line,cancel):clicked.append(line['text'])
    controller=DesktopActions(Settings(tmp_path),FakeRuntime(),catalog=Catalog(),screen=Screen())
    result=await controller.execute(ComputerAction(action='deathmatch',app='cs2'),async_noop)
    assert clicked==['JOGAR','CRIAÇÃO DE PARTIDAS','MATA-MATA','JOGAR']
    assert result['verified'] and result['state']=='searching'
    controller.close()


@pytest.mark.asyncio
async def test_moving_a_window_invalidates_observed_click(monkeypatch):
    import time,win32gui,win32api
    from pacoca.screen import Screen
    monkeypatch.setattr(win32gui,'GetForegroundWindow',lambda:1)
    monkeypatch.setattr(win32gui,'GetClientRect',lambda hwnd:(0,0,900,600))
    monkeypatch.setattr(win32gui,'ClientToScreen',lambda hwnd,point:(300,300))
    monkeypatch.setattr(win32api,'SetCursorPos',lambda *_:pytest.fail('Stale coordinates must never be clicked'))
    observation={'time':time.monotonic(),'geometry':{'left':100,'top':100,'width':900,'height':600,'scale':1}}
    with pytest.raises(RuntimeError,match='moveu'):
        await Screen().click(1,observation,{'rect':(10,10,20,20)},asyncio.Event())


@pytest.mark.asyncio
async def test_first_song_waits_for_native_media_registration_without_double_play(tmp_path,monkeypatch):
    import pacoca.actions as module
    async def instant(_):pass
    monkeypatch.setattr(module.asyncio,'sleep',instant)
    played=[]
    class Catalog:
        async def open(self,*args):return {'verified':True,'focused':True,'window':{'id':1}}
    class UI:
        def search(self,hwnd,query):return True
        def tracks(self,*args):return [{'label':'Numb Linkin Park 3:06'}]
        def play_track(self,*args):played.append(args)
    class Media:
        calls=0
        async def state(self):
            self.calls+=1
            if self.calls<3:raise RuntimeError('Session not registered yet')
            return {'title':'Numb','artist':'Linkin Park','status':'playing'}
        async def command(self,*args):pytest.fail('Do not play again after the UI accepted the selected song')
    controller=DesktopActions(Settings(tmp_path),FakeRuntime(),catalog=Catalog(),spotify_ui=UI(),media=Media())
    result=await controller.execute(ComputerAction(action='play',app='spotify',query='Numb Linkin Park'),async_noop)
    assert result['verified'] and len(played)==1
    controller.close()


def test_song_search_excludes_artist_cards_and_library_playlists():
    from pacoca.media import SpotifyUI
    class Control:
        def __init__(self,name,kind='DataItem',parent=None,children=()):
            self.element_info=SimpleNamespace(name=name,control_type=kind);self.owner=parent;self.children=children
        def parent(self):return self.owner
        def descendants(self):return list(self.children)
    library=Control('Sua Biblioteca','DataGrid')
    controls=[Control('Numb Linkin Park Playlist',parent=library),Control('Numb Linkin Park Álbum'),Control('Numb Linkin Park 3:06')]
    ui=SpotifyUI();ui._run=lambda hwnd,operation:operation(SimpleNamespace(descendants=lambda:controls))
    assert ui.tracks(1,'Numb Linkin Park')==[{'label':'Numb Linkin Park 3:06','score':1}]
