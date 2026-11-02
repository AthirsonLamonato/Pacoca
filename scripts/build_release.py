"""Build one Windows installer; install the pinned chat model automatically."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import platform
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def run(args,**kwargs):
    print("BUILD",str(args[0]),flush=True)
    log_dir=ROOT/'build';log_dir.mkdir(exist_ok=True)
    name='installer.log' if str(args[0]).lower().endswith('iscc.exe') else 'executable.log' if 'PyInstaller' in [str(a) for a in args] else 'native.log' if 'scripts/check_distribution.py' in [str(a) for a in args] else 'tools.log'
    with (log_dir/name).open('w',encoding='utf-8') as output:
        result=subprocess.run([str(a) for a in args],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,**kwargs)
    if result.returncode:
        print((log_dir/name).read_text(encoding='utf-8',errors='replace')[-5000:],flush=True)
        raise RuntimeError('Build failed; see '+str(log_dir/name))


def build_environment():
    env=os.environ.copy()
    if os.name=='nt':
        windows=Path(os.environ.get('SystemRoot',r'C:\Windows'))
        # Third-party programs on PATH can supply same-named incompatible DLLs.
        env['PATH']=';'.join(str(p) for p in [Path(sys.executable).parent,
            windows/'System32',windows,windows/'System32/WindowsPowerShell/v1.0'])
    for name in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):
        env.pop(name,None)
    return env


def download(url,path,digest=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        urllib.request.urlretrieve(url,path)
    if digest and hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise RuntimeError("Build tool checksum mismatch: "+path.name)


def icon():
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtCore import Qt
    renderer=QSvgRenderer(str(ROOT/'src/pacoca/ui/icon.svg'))
    img=QImage(256,256,QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter=QPainter(img);renderer.render(painter);painter.end()
    png=ROOT/'build/icon.png';png.parent.mkdir(exist_ok=True);img.save(str(png))
    from PIL import Image
    Image.open(png).save(ROOT/'packaging/icon.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])


def copy_assets():
    manifest=json.loads((ROOT/'assets/manifest.json').read_text())
    dest=ROOT/'build/offline-assets'
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'assets/manifest.json',dest/'manifest.json')
    required={'engine':ROOT/'assets/engine','engine-cuda':ROOT/'assets/engine-cuda',
              'browser':ROOT/'assets/browser','models/whisper':ROOT/'assets/models/whisper'}
    for rel,source in required.items():
        if not source.exists():
            raise FileNotFoundError("Prepare os recursos offline antes do build: "+str(source))
        shutil.copytree(source,dest/rel,dirs_exist_ok=True)
    for rel in [manifest['model'],manifest['voice'],manifest['voice']+'.json']:
        target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or target.stat().st_size!=(ROOT/'assets'/rel).stat().st_size:
            shutil.copy2(ROOT/'assets'/rel,target)


def model_download_recipe():
    manifest=json.loads((ROOT/'assets/manifest.json').read_text())
    lock=json.loads((ROOT/'packaging/assets.lock.json').read_text())
    item=next(i for i in lock['items'] if i['path']==manifest['model'])
    if not item['url'].startswith('https://huggingface.co/') or len(item['sha256'])!=64:
        raise ValueError('The model download must use its pinned official URL and SHA-256.')
    advanced=next(i for i in lock['items'] if i['path']==manifest['models']['advanced']['path'])
    values={'ModelURL':item['url'],'ModelHash':item['sha256'],
            'ModelFile':Path(item['path']).name,'ModelSize':item['size'],
            'AdvancedURL':advanced['url'],'AdvancedHash':advanced['sha256'],
            'AdvancedFile':Path(advanced['path']).name,'AdvancedSize':advanced['size']}
    (ROOT/'build/model-download.iss').write_text('\n'.join(
        '#define '+key+' '+(str(value) if isinstance(value,int) else '"'+value+'"')
        for key,value in values.items())+'\n',encoding='utf-8')


def sources_and_notices():
    source=ROOT/'build/source';source.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source/'Pacoca-source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ['src','scripts','packaging','tests_next','docs']:
            for path in (ROOT/folder).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:
                    z.write(path,path.relative_to(ROOT))
        for name in ['pyproject.toml','run-pacoca.py','README.md','README.legacy.md','LICENSE.desktop']:
            z.write(ROOT/name,name)
    licenses=ROOT/'build/licenses';licenses.mkdir(parents=True,exist_ok=True)
    for dist in importlib.metadata.distributions():
        name=dist.metadata.get('Name','package')
        if not dist.files:
            continue
        for file in dist.files:
            if any(w in str(file).upper() for w in ('LICENSE','COPYING','NOTICE')):
                path=Path(dist.locate_file(file))
                if path.is_file() and path.stat().st_size<5_000_000:
                    target=licenses/name/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    urls={
      'llama-MIT.txt':'https://raw.githubusercontent.com/ggml-org/llama.cpp/b12032/LICENSE',
      'Qwen-APACHE.txt':'https://huggingface.co/Qwen/Qwen3-8B/resolve/main/LICENSE',
      'Piper-GPL3.txt':'https://raw.githubusercontent.com/OHF-Voice/piper1-gpl/main/COPYING',
    }
    for name,url in urls.items():
        download(url,licenses/name)
    shutil.copy2(ROOT/'assets/licenses/voice-MODEL_CARD',licenses/'voice-MODEL_CARD.txt')
    shutil.copy2(ROOT/'packaging/DISTRIBUTION.txt',licenses/'DISTRIBUTION.txt')
    # The source distribution for the exact Piper version is included, not just a link.
    version=importlib.metadata.version('piper-tts')
    with urllib.request.urlopen('https://pypi.org/pypi/piper-tts/'+version+'/json') as r:
        metadata=json.load(r)
    sdist=next(u for u in metadata['urls'] if u['packagetype']=='sdist')
    download(sdist['url'],source/sdist['filename'],sdist['digests']['sha256'])
    sys.path.insert(0,str(ROOT/'src'))
    from pacoca import __version__
    public=ROOT/'release';public.mkdir(exist_ok=True)
    with zipfile.ZipFile(public/f'Pacoca-sources-{__version__}.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for folder in (source,licenses):
            for path in folder.rglob('*'):
                if path.is_file():archive.write(path,path.relative_to(ROOT/'build').as_posix())


def inno_compiler():
    compiler=ROOT/'.tools/inno/ISCC.exe'
    if compiler.exists():
        return compiler
    installer=ROOT/'.tools/innosetup.exe'
    download('https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe',installer,
             '8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0')
    run([installer,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/DIR='+str(compiler.parent)],
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if not compiler.exists():
        raise RuntimeError('Inno compiler not installed')
    return compiler


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--skip-executable',action='store_true')
    p.add_argument('--executable-only',action='store_true')
    args=p.parse_args()
    icon()
    if not args.skip_executable:
        dependencies=(ROOT/'packaging/requirements.lock').read_text(encoding='utf-8-sig').encode('utf-8')
        identity=hashlib.sha256(dependencies+platform.python_version().encode()+b'pacoca-runtime-2').hexdigest()
        (ROOT/'src/pacoca/runtime-id.txt').write_text(identity+'\n',encoding='utf-8')
        # A module edited during an earlier analysis can predate the cached PYZ,
        # making incremental timestamp checks reuse stale code. Always rebuild.
        run([sys.executable,'-m','PyInstaller','packaging/pacoca.spec','--noconfirm','--clean'],env=build_environment())
    run([sys.executable,'scripts/verify_bundle.py'])
    run([sys.executable,'scripts/check_distribution.py','--exe','dist/Pacoca/Pacoca.exe',
         '--assets','assets','--name','build-native','--native'])
    if args.executable_only:
        return
    copy_assets()
    model_download_recipe()
    sources_and_notices()
    compiler=inno_compiler()
    run([compiler,'/DProjectRoot='+str(ROOT),ROOT/'packaging/installer.iss'])
    installer=ROOT/'release/Pacoca-Setup.exe'
    h=hashlib.sha256()
    with installer.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            h.update(block)
    (installer.parent/'SHA256SUMS.txt').write_text(h.hexdigest()+'  Pacoca-Setup.exe\n')
    print('READY',installer,installer.stat().st_size,flush=True)


if __name__=='__main__':
    main()
