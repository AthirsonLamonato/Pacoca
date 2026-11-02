# Build with: .venv/Scripts/python -m PyInstaller packaging/pacoca.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_all,collect_data_files,collect_submodules
from pocketsphinx import get_model_path

root=Path(SPECPATH).parent
datas=[(str(root/'src/pacoca/ui'),'pacoca/ui'),
       (str(root/'src/pacoca/update_helper.ps1'),'pacoca'),
       (str(root/'src/pacoca/runtime-id.txt'),'pacoca'),
       (str(root/'src/pacoca/wake.dic'),'pacoca'),
       (str(root/'assets/models/whisper-base'),'speech/whisper-base'),
       # Decoder probes this namespace while constructing its default config,
       # even when all actual acoustic/dictionary paths are explicit.
       (str(Path(get_model_path())/'en-us/en-us/README'),'pocketsphinx/model'),
       (str(Path(get_model_path())/'en-us/en-us'),'wakeword/en-us')]
binaries=[]
hiddenimports=[]
hiddenimports+=['pocketsphinx._pocketsphinx','win32com.client.dynamic','pythoncom']
for package in ('piper','faster_whisper','ctranslate2','onnxruntime'):
    data,bins,hidden=collect_all(package)
    datas+=data;binaries+=bins;hiddenimports+=hidden
hiddenimports+=['uvicorn.logging','uvicorn.loops.auto','uvicorn.protocols.http.h11_impl',
                'uvicorn.protocols.websockets.websockets_impl','uvicorn.lifespan.on',
                'win32timezone','pycaw.pycaw','pywinauto','comtypes','pypdf',
                'ask_sdk_webservice_support.verifier']
datas+=collect_data_files('playwright')

a=Analysis([str(root/'run-pacoca.py')],pathex=[str(root/'src')],binaries=binaries,datas=datas,
           hiddenimports=hiddenimports,hookspath=[],runtime_hooks=[],
           excludes=['tkinter','PyQt5','PyQt6','torch','tensorflow','matplotlib','pandas','scipy','sklearn','pytest','IPython'])
# Qt uses the unversioned ICU C API supplied by supported Windows versions.
# Never shadow it with a same-named vendor ICU (for example Poppler's ICU 78).
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in
            {'icuuc.dll','icuin.dll','icu.dll'} and not Path(entry[0]).name.lower().startswith('icudt')]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='Pacoca',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,icon=str(root/'packaging/icon.ico'),
        version=str(root/'packaging/version.txt'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Pacoca')
