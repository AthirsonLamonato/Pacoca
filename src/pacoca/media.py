"""Windows media controls and the Spotify desktop accessibility interface.

No Spotify developer API, credentials or private service endpoints are used.
"""
import asyncio
import re
import time

from .routing import normalized


class WindowsMedia:
    async def session(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        manager=await GlobalSystemMediaTransportControlsSessionManager.request_async()
        sessions=[s for s in manager.get_sessions() if 'spotify' in s.source_app_user_model_id.casefold()]
        if len(sessions)!=1:
            raise RuntimeError('Não encontrei uma sessão única de reprodução do Spotify. Abra uma faixa no aplicativo para eu controlar.')
        return sessions[0]

    async def state(self):
        session=await self.session()
        media=await session.try_get_media_properties_async()
        status=session.get_playback_info().playback_status
        timeline=session.get_timeline_properties()
        return {'title':media.title,'artist':media.artist,'status':status.name.casefold(),
                'position':timeline.position.total_seconds(),'source':session.source_app_user_model_id}

    async def command(self,action):
        session=await self.session()
        operations={'pause':session.try_pause_async,'resume':session.try_play_async,
                    'next':session.try_skip_next_async,'previous':session.try_skip_previous_async}
        if not await operations[action]():raise RuntimeError('O Spotify não aceitou esse controle de mídia.')
        for _ in range(10):
            await asyncio.sleep(.2)
            state=await self.state()
            if action=='pause' and state['status']=='paused' or action=='resume' and state['status']=='playing':return state
            if action in ('next','previous'):return state
        raise RuntimeError('O comando foi enviado, mas o estado de reprodução não foi confirmado.')


class SpotifyUI:
    """Each call resolves fresh UIA controls in the already verified Spotify window."""
    def _run(self,hwnd,operation,*args):
        import comtypes
        comtypes.CoInitialize()
        try:
            from pywinauto import Desktop
            root=Desktop(backend='uia').window(handle=hwnd)
            import psutil
            if psutil.Process(root.process_id()).name().casefold()!='spotify.exe':raise RuntimeError('A janela do Spotify mudou. Peça novamente.')
            return operation(root,*args)
        finally:comtypes.CoUninitialize()

    def labels(self,hwnd):
        return self._run(hwnd,lambda root:[c.element_info.name for c in root.descendants()[:500] if c.element_info.name])

    def search(self,hwnd,query):
        def operation(root):
            controls=root.descendants()[:500]
            fields=[c for c in controls if c.element_info.control_type in ('Edit','ComboBox') and any(
                word in normalized(c.element_info.name+' '+c.element_info.automation_id) for word in ('buscar','pesquisar','search','quer ouvir','quer escutar','want to play'))]
            if len(fields)!=1:
                buttons=[c for c in controls if c.element_info.control_type in ('Button','Hyperlink') and normalized(c.element_info.name).strip() in ('buscar','pesquisar','search')]
                if len(buttons)==1:
                    buttons[0].invoke()
                    return False
                raise RuntimeError('Não consegui identificar o campo de busca do Spotify nesta interface.')
            field=fields[0]
            try:field.iface_value.SetValue(query)
            except Exception as exc:
                raise RuntimeError('O Spotify não permitiu preencher a busca por acessibilidade. Confira se a janela está disponível.') from exc
            return True
        return self._run(hwnd,operation)

    def tracks(self,hwnd,query):
        terms={w for w in normalized(query).split() if len(w)>1 and w not in {'de','do','da','the','uma','musica'}}
        def operation(root):
            found=[]
            for c in root.descendants()[:600]:
                name=c.element_info.name
                if c.element_info.control_type not in ('DataItem','ListItem') or not name:continue
                parent=c;library=False
                for _ in range(5):
                    parent=parent.parent()
                    if parent is None:break
                    if normalized(parent.element_info.name).strip() in ('sua biblioteca','your library'):library=True;break
                if library:continue
                detail=' '.join([name,*[child.element_info.name for child in c.descendants()[:70]]])
                # Song rows expose a duration. Album/artist/library cards do not.
                if not re.search(r'\b\d{1,2}:\d{2}\b',detail):continue
                score=sum(t in normalized(detail) for t in terms)/max(1,len(terms))
                if score>=.8:found.append({'label':name,'score':score})
            return found[:12]
        return self._run(hwnd,operation)

    def play_track(self,hwnd,label):
        def operation(root):
            rows=[c for c in root.descendants()[:600] if c.element_info.control_type in ('DataItem','ListItem') and c.element_info.name==label]
            if len(rows)!=1:raise RuntimeError('O resultado da busca mudou; nenhuma faixa foi escolhida.')
            row=rows[0]
            buttons=[c for c in row.descendants() if c.element_info.control_type=='Button' and normalized(c.element_info.name).startswith(('reproduzir','tocar','play'))]
            if len(buttons)==1:buttons[0].invoke()
            else:
                try:row.invoke()
                except (AttributeError,NotImplementedError):row.double_click_input()
        return self._run(hwnd,operation)

    def device_picker(self,hwnd):
        def operation(root):
            controls=root.descendants()[:3000]
            if any(normalized(c.element_info.name).strip()=='connect' for c in controls):return
            buttons=[c for c in controls if c.element_info.control_type=='Button' and any(
                key in normalized(c.element_info.name) for key in ('conectar a um dispositivo','conectar dispositivo','connect to a device','connect to device','dispositivos disponiveis','escolher dispositivo'))]
            if len(buttons)!=1:raise RuntimeError('Não encontrei o seletor de dispositivos do Spotify.')
            buttons[0].invoke()
        return self._run(hwnd,operation)

    def devices(self,hwnd):
        def operation(root):
            controls=root.descendants()[:3000]
            output=[]
            for c in controls:
                name=c.element_info.name.strip()
                if c.element_info.control_type not in ('Button','ListItem','RadioButton') or not name or normalized(name).startswith(('mais opcoes','more options')):continue
                if any(w in normalized(name) for w in ('alexa','echo','iphone','android','galaxy','celular','este computador','this computer','pc de','computador de')):
                    output.append({'label':name,'selected':self._selected(c)})
            return output
        return self._run(hwnd,operation)

    @staticmethod
    def _selected(control):
        try:return bool(control.is_selected())
        except Exception:
            text=normalized(control.element_info.name)
            return any(s in text for s in ('tocando neste','listening on','ouvindo em','dispositivo atual','current device'))

    def choose_device(self,hwnd,label):
        def operation(root):
            matches=[c for c in root.descendants()[:3000] if c.element_info.name.strip()==label and c.element_info.control_type in ('Button','ListItem','RadioButton')]
            if len(matches)!=1:raise RuntimeError('A lista de dispositivos mudou. Nenhum dispositivo foi selecionado.')
            control=matches[0]
            try:control.select()
            except (AttributeError,NotImplementedError):control.invoke()
        return self._run(hwnd,operation)


def resolve_device(devices,target,preferred=''):
    value=normalized(target).strip()
    if value in ('aqui','pc','computador','neste pc'):
        terms=('este computador','this computer','este pc')
    elif value=='alexa':terms=('alexa','echo')
    elif value in ('celular','telefone','cel'):terms=('iphone','android','galaxy','celular','telefone')
    else:terms=(value,)
    matches=[d for d in devices if any(term in normalized(d['label']) for term in terms)]
    if len(matches)>1 and preferred:
        exact=[d for d in matches if normalized(d['label'])==normalized(preferred)]
        if len(exact)==1:return exact[0]
    return matches[0] if len(matches)==1 else None
