"""Resource policy shared by inference, application actions and updates."""
from __future__ import annotations

import threading
import time

GAME_PROCESSES = frozenset({
    'cs2.exe','csgo.exe','valorant-win64-shipping.exe','valorant.exe',
    'league of legends.exe','pointblank.exe','gta5.exe','gta5_enhanced.exe',
    'fortniteclient-win64-shipping.exe','r5apex.exe','overwatch.exe',
    'dota2.exe','rocketleague.exe','minecraft.exe',
})


class ResourcePolicy:
    def __init__(self, settings, process_source=None, clock=time.monotonic):
        self.settings=settings
        self._source=process_source
        self.clock=clock
        self._checked=-10
        self._games=[]
        self._lock=threading.Lock()

    def games(self):
        with self._lock:
            if self.clock()-self._checked<2:
                return list(self._games)
            import psutil
            source=self._source or (lambda:psutil.process_iter(['name']))
            found=[]
            for process in source():
                try:
                    name=process if isinstance(process,str) else process.info.get('name','')
                    if (name or '').casefold() in GAME_PROCESSES:
                        found.append(name)
                except (psutil.Error,OSError):
                    continue
            self._games=sorted(set(found));self._checked=self.clock()
            return list(self._games)

    def profile(self):
        requested=self.settings.get('model_profile','light')
        if requested=='advanced' and self.settings.get('game_guard',True) and self.games():
            return 'light'
        return requested

    def info(self):
        games=self.games()
        return {'profile':self.profile(),'requested_profile':self.settings.get('model_profile','light'),
                'games':games,'gpu_reserved_for_games':bool(games),
                'cpu_threads':max(1,min(4,int(self.settings.get('cpu_threads',2))))}
