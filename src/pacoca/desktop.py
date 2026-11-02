from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import threading
import time

from .config import Settings


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Paçoca · Sua inteligência pessoal")
    parser.add_argument("--web",action="store_true",help="Abrir no navegador padrão (desenvolvimento)")
    parser.add_argument("--headless",action="store_true",help="Executar o servidor local sem janela")
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--minimized",action="store_true")
    parser.add_argument("--connection-file",help="Gravar endereço de conexão para testes locais")
    parser.add_argument("--native-ready-file",help="Registrar a renderização da janela para diagnóstico")
    parser.add_argument('--update-health-file',help='Verificação da janela após uma atualização autenticada')
    parser.add_argument('--update-feed',help='Canal de atualização assinado; localhost permite testes de distribuição')
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE","1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
    settings = Settings()
    instance_lock=None
    if getattr(sys,'frozen',False) and os.name=='nt':
        import msvcrt
        instance_lock=(settings.directory/'instance.lock').open('a+b')
        # Reading a byte locked by the first instance raises on Windows too.
        if os.fstat(instance_lock.fileno()).st_size == 0:
            instance_lock.write(b'1');instance_lock.flush()
        instance_lock.seek(0)
        try:
            msvcrt.locking(instance_lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            try:
                import httpx
                old=json.loads((settings.directory/'instance.json').read_text())
                httpx.post(f"http://127.0.0.1:{int(old['port'])}/api/activate",headers={'X-Pacoca-Token':old['token']},timeout=5,trust_env=False)
            except (OSError,ValueError,httpx.HTTPError):
                pass  # The first instance may still be initializing.
            finally:
                instance_lock.close()
            return
    handler = RotatingFileHandler(settings.directory / "pacoca.log",maxBytes=2_000_000,backupCount=3,encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    from .app import create_app
    import uvicorn
    app = create_app(settings,update_feed=args.update_feed)
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    sock.bind(("127.0.0.1",args.port))
    sock.listen(128)
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/#token={app.state.token}"
    instance={'url':url,'port':port,'token':app.state.token,'pid':os.getpid()}
    (settings.directory/'instance.json').write_text(json.dumps(instance),encoding='utf-8')
    if args.connection_file:
        Path(args.connection_file).write_text(json.dumps(instance),encoding="utf-8")
    server = uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="warning",access_log=False,log_config=None))
    app.state.shutdown=lambda:setattr(server,'should_exit',True)
    activation=threading.Event()
    app.state.activate=activation.set
    if args.headless:
        server.run(sockets=[sock])
        return
    thread = threading.Thread(target=server.run,kwargs={"sockets":[sock]},daemon=True)
    thread.start()
    if args.web:
        import webbrowser
        webbrowser.open(url)
        try:
            while thread.is_alive():
                time.sleep(.5)
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(15)
        return
    run_window(url,server,thread,settings,args.minimized,activation,args.native_ready_file,args.update_health_file)


def run_window(url,server,thread,settings,minimized=False,activation=None,ready_file=None,health_file=None):
    # The keyword microphone must continue running with the window minimized.
    flags=os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS','')
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS']=flags+' --disable-background-timer-throttling --disable-renderer-backgrounding'
    from PySide6.QtCore import QObject, QUrl, Slot, Qt, QTimer, qVersion
    from PySide6.QtGui import QIcon, QAction, QDesktopServices
    from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QSystemTrayIcon, QMenu
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
    from PySide6.QtWebChannel import QWebChannel
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Paçoca")
    app.setOrganizationName("Pacoca")
    app.setStyle("Fusion")
    icon = QIcon(str(Path(__file__).parent / "ui" / "icon.svg"))
    app.setWindowIcon(icon)

    class Bridge(QObject):
        @Slot(result=str)
        def chooseFolder(self):
            return QFileDialog.getExistingDirectory(window,"Escolha uma pasta para a Paçoca conhecer")
        @Slot(result=str)
        def chooseApplication(self):
            return QFileDialog.getOpenFileName(window,'Escolha o aplicativo instalado','','Aplicativos (*.exe)')[0]

    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self,target,kind,main_frame):
            if target.scheme() in ("http","https") and target.host()=="127.0.0.1" and target.port()==QUrl(url).port():
                return True
            if target.scheme() in ("http","https") and kind==QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                QDesktopServices.openUrl(target)
            return False

    class Window(QMainWindow):
        def closeEvent(self,event):
            server.should_exit=True
            event.accept()

    window=Window()
    window.setWindowTitle("Paçoca · Sua inteligência pessoal")
    window.resize(1320,900)
    window.setMinimumSize(820,620)
    profile=QWebEngineProfile("Pacoca",window)
    profile.setPersistentStoragePath(str(settings.directory / "WebView"))
    profile.setCachePath(str(settings.directory / "WebCache"))
    view=QWebEngineView(window)
    page=LocalPage(profile,view)
    view.setPage(page)
    from PySide6.QtWebEngineCore import QWebEngineSettings
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,False)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False)
    def permission(permission):
        from PySide6.QtWebEngineCore import QWebEnginePermission
        if permission.origin().host()=="127.0.0.1" and permission.permissionType()==QWebEnginePermission.PermissionType.MediaAudioCapture:
            permission.grant()
        else:
            permission.deny()
    page.permissionRequested.connect(permission)
    channel=QWebChannel(page)
    bridge=Bridge(window)
    channel.registerObject("native",bridge)
    page.setWebChannel(channel)
    from PySide6.QtCore import QFile
    source=QFile(":/qtwebchannel/qwebchannel.js")
    source.open(QFile.OpenModeFlag.ReadOnly)
    js=bytes(source.readAll()).decode("utf-8")
    source.close()
    script=QWebEngineScript()
    script.setName("pacoca-native")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setSourceCode(js+"\nnew QWebChannel(qt.webChannelTransport, channel => { window.pacocaNative = channel.objects.native; });")
    page.scripts().insert(script)
    def download(request):
        target,_=QFileDialog.getSaveFileName(window,"Salvar exportação",request.downloadFileName(),"JSON (*.json)")
        if target:
            request.setDownloadDirectory(str(Path(target).parent))
            request.setDownloadFileName(Path(target).name)
            request.accept()
        else:
            request.cancel()
    profile.downloadRequested.connect(download)
    window.setCentralWidget(view)
    timer=QTimer(window)
    def check_events():
        if server.should_exit:
            app.quit()
        elif activation and activation.is_set():
            activation.clear();window.showNormal();window.activateWindow()
    timer.timeout.connect(check_events)
    timer.start(300)
    if ready_file or health_file:
        from . import __version__
        health_timer=QTimer(window)
        health_timer.setInterval(250)
        def probe():
            def rendered(valid):
                if valid:
                    health_timer.stop()
                    result={'rendered':True,'qt_version':qVersion(),'version':__version__,'pid':os.getpid()}
                    for filename in (ready_file,health_file):
                        if filename:Path(filename).write_text(json.dumps(result),encoding='utf-8')
            page.runJavaScript("Boolean(document.getElementById('prompt') && typeof state !== 'undefined' && state.connected && state.status)",rendered)
        health_timer.timeout.connect(probe)
        page.loadFinished.connect(lambda ok:health_timer.start() if ok else None)
    view.setUrl(QUrl(url))
    tray=QSystemTrayIcon(icon,window)
    tray.setToolTip("Paçoca · Sua inteligência pessoal")
    menu=QMenu()
    show=menu.addAction("Abrir Paçoca")
    show.triggered.connect(lambda:(window.showNormal(),window.activateWindow()))
    pause=menu.addAction('Pausar microfone')
    pause.triggered.connect(lambda:page.runJavaScript('safely(pauseMicrophone)()'))
    menu.addSeparator()
    quit_action=menu.addAction("Encerrar Paçoca")
    quit_action.triggered.connect(window.close)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason:window.showNormal() if reason==QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()
    if minimized:
        window.showMinimized()
    else:
        window.show()
    app.exec()
    server.should_exit=True
    thread.join(20)


if __name__ == "__main__":
    main()
