"""Windows adapters. No model-generated shell code is executed."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time


def require_windows():
    if os.name != "nt":
        raise RuntimeError("Essa ação está disponível somente no Windows.")


def windows():
    require_windows()
    import win32gui
    import win32process
    import psutil
    result = []
    def visit(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and title:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                result.append(dict(id=hwnd,title=title[:180],process=psutil.Process(pid).name(),pid=pid))
            except (OSError, psutil.Error):
                pass
    win32gui.EnumWindows(visit, None)
    return result[:60]


def focus_window(id):
    require_windows()
    import win32gui
    if not any(w["id"] == id for w in windows()):
        raise ValueError("A janela não está mais disponível. Consulte as janelas novamente.")
    win32gui.ShowWindow(id, 9)
    win32gui.SetForegroundWindow(id)
    if win32gui.GetForegroundWindow() != id:
        raise RuntimeError("O Windows não permitiu colocar essa janela em primeiro plano.")
    return {"window_id": id, "verified": True}


def applications():
    require_windows()
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
        capture_output=True, timeout=20, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if result.returncode:
        raise RuntimeError("Não consegui consultar os aplicativos do menu Iniciar.")
    entries = json.loads(result.stdout.decode("utf-8-sig", errors="replace") or "[]")
    if isinstance(entries, dict):
        entries = [entries]
    return [{"id": a["AppID"], "name": a["Name"]} for a in entries]


def open_application(query):
    require_windows()
    apps = applications()
    exact = [a for a in apps if query.casefold() in (a["id"].casefold(),a["name"].casefold())]
    matches = exact or [a for a in apps if query.casefold() in a["name"].casefold()]
    if len(matches) != 1:
        return {"verified":False,"needs_clarification":True,"candidates":matches[:12],
                "message":"Escolha um aplicativo da lista." if matches else "Não encontrei esse aplicativo. Consulte os aplicativos instalados."}
    app = matches[0]
    before = {w["id"] for w in windows()}
    # App IDs come exclusively from Get-StartApps, never from generated shell text.
    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app["id"]], creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    import win32gui
    for _ in range(30):
        current = windows()
        changed = [w for w in current if w["id"] not in before]
        active = next((w for w in current if w["id"] == win32gui.GetForegroundWindow()), None)
        if changed or (active and any(t.casefold() in active["title"].casefold() for t in app["name"].split() if len(t)>3)):
            return {"application":app["name"],"verified":True,"windows":changed or [active]}
        time.sleep(.15)
    return {"application":app["name"],"verified":False,"message":"Pedi a abertura, mas não confirmei a janela."}


def open_path(path):
    require_windows()
    before = {w["id"] for w in windows()}
    os.startfile(str(path))
    for _ in range(20):
        new = [w for w in windows() if w["id"] not in before]
        matching = [w for w in windows() if path.name.casefold() in w["title"].casefold()]
        if new or matching:
            return {"path":str(path),"verified":True,"windows":new or matching}
        time.sleep(.15)
    return {"path":str(path),"verified":False,"message":"Solicitação enviada; janela não confirmada."}


def volume(level):
    require_windows()
    import comtypes
    comtypes.CoInitialize()
    try:
        from pycaw.pycaw import AudioUtilities
        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        if level is not None:
            endpoint.SetMasterVolumeLevelScalar(level / 100, None)
        current = round(endpoint.GetMasterVolumeLevelScalar()*100)
        return {"volume":current,"verified":level is None or abs(current-level)<=1}
    finally:
        comtypes.CoUninitialize()


def inspect_controls(window_id):
    require_windows()
    import comtypes
    comtypes.CoInitialize()
    try:
        from pywinauto import Desktop
        root = Desktop(backend="uia").window(handle=window_id)
        controls = []
        for i, child in enumerate(root.descendants()[:100]):
            info = child.element_info
            if info.name or info.automation_id:
                controls.append(dict(ref=i,name=info.name[:150],type=info.control_type,automation_id=info.automation_id))
        return {"window_id":window_id,"title":root.window_text(),"controls":controls}
    finally:
        comtypes.CoUninitialize()


def interact_control(window_id, action, reference=None, text=""):
    require_windows()
    import comtypes
    comtypes.CoInitialize()
    try:
        from pywinauto import Desktop
        root = Desktop(backend="uia").window(handle=window_id)
        if action == "type":
            if reference is None:
                raise ValueError("Escolha um campo observado antes de digitar.")
            field = root.descendants()[reference]
            if field.element_info.control_type != "Edit":
                raise ValueError("O controle escolhido não é um campo de texto.")
            field.set_edit_text(text)
            return {"verified":field.window_text()==text}
        if action == "click":
            if reference is None:
                raise ValueError("Escolha um controle observado antes de clicar.")
            child = root.descendants()[reference]
            try:
                child.invoke()
            except (AttributeError,NotImplementedError):
                child.click_input()
            return {"verified":False,"message":"Clique enviado. Consulte a janela para verificar o resultado."}
        raise ValueError("Ação de janela inválida.")
    finally:
        comtypes.CoUninitialize()
