"""Reject a stale executable before producing the offline installer."""
import hashlib
import marshal
import os
from pathlib import Path
from types import CodeType

from PyInstaller.archive.readers import ZlibArchiveReader

ROOT=Path(__file__).resolve().parents[1]


def normalized(code):
    return code.replace(co_filename='',co_consts=tuple(normalized(x) if isinstance(x,CodeType) else x for x in code.co_consts))


def main():
    archive=ZlibArchiveReader(str(ROOT/'build/pacoca/PYZ-00.pyz'))
    stale=[]
    for path in (ROOT/'src/pacoca').glob('*.py'):
        name='pacoca' if path.stem=='__init__' else 'pacoca.'+path.stem
        if name=='pacoca.__main__':
            continue
        packed=archive.extract(name)
        source=compile(path.read_text(encoding='utf-8'),str(path),'exec')
        if marshal.dumps(normalized(packed))!=marshal.dumps(normalized(source)):
            stale.append(str(path.relative_to(ROOT)))
    for path in (ROOT/'src/pacoca/ui').glob('*'):
        if path.is_file():
            bundled=ROOT/'dist/Pacoca/_internal/pacoca/ui'/path.name
            if not bundled.exists() or hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(bundled.read_bytes()).digest():
                stale.append(str(path.relative_to(ROOT)))
    for name in ('update_helper.ps1','runtime-id.txt'):
        source=ROOT/'src/pacoca'/name
        bundled=ROOT/'dist/Pacoca/_internal/pacoca'/name
        if not bundled.exists() or source.read_bytes()!=bundled.read_bytes():
            stale.append(str(source.relative_to(ROOT)))
    if os.name=='nt':
        for name in ('icuuc.dll','icudt78.dll'):
            if list((ROOT/'dist/Pacoca').rglob(name)):
                stale.append('incompatible bundled Windows ICU: '+name)
    if stale:
        raise RuntimeError('Rebuild the executable. Stale files: '+', '.join(stale))
    print('Executable code and UI match the current source.',flush=True)


if __name__=='__main__':main()
