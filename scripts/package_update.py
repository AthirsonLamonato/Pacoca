"""Create authenticated application/runtime updates without shipping AI models."""
import argparse
import base64
import json
from pathlib import Path
import sys
import zipfile

from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pacoca import __version__
from pacoca.update_format import sha256,validate_package,decode_manifest,application_path
from pacoca.updates import runtime_identity


def package(root,output,paths,version,identity,kind,base_url):
    records=[]
    for path in paths:
        rel=path.relative_to(root).as_posix();application_path(rel)
        records.append({'path':rel,'size':path.stat().st_size,'sha256':sha256(path)})
    name=f'Pacoca-{version}-{kind}.zip';target=output/name
    metadata={'version':version,'runtime_id':identity,'files':records,'remove':[]}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=False) as z:
        for path in paths:z.write(path,path.relative_to(root).as_posix())
        z.writestr('package.json',json.dumps(metadata,separators=(',',':')))
    result={'kind':kind,'from_runtime':identity if kind=='app' else '*','runtime_id':identity,
            'url':base_url.rstrip('/')+'/'+name,'size':target.stat().st_size,'sha256':sha256(target)}
    validate_package(target,result,version)
    print(kind,name,result['size'],flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dist',type=Path,default=ROOT/'dist/Pacoca')
    p.add_argument('--output',type=Path,default=ROOT/'release')
    p.add_argument('--key',type=Path,default=ROOT/'.tools/update-signing-key.pem')
    p.add_argument('--base-url',default='')
    p.add_argument('--app-only',action='store_true')
    p.add_argument('--notes',default='Modo leve, atualizações automáticas e comandos de aplicativos, jogos e Spotify.')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    identity=runtime_identity()
    bundled=(args.dist/'_internal/pacoca/runtime-id.txt').read_text().strip()
    if bundled!=identity:raise RuntimeError('Rebuild with the current dependency identity first')
    paths=sorted(p for p in args.dist.rglob('*') if p.is_file() and (p.name=='Pacoca.exe' and p.parent==args.dist or p.relative_to(args.dist).parts[0]=='_internal'))
    app_paths=[p for p in paths if p.name=='Pacoca.exe' and p.parent==args.dist or p.is_relative_to(args.dist/'_internal/pacoca')]
    base=args.base_url or f'https://github.com/AthirsonLamonato/Pacoca/releases/download/v{__version__}'
    packages=[package(args.dist,args.output,app_paths,__version__,identity,'app',base)]
    if not args.app_only:packages.append(package(args.dist,args.output,paths,__version__,identity,'runtime',base))
    payload={'schema':1,'app_id':'pacoca-desktop','database_schema':1,'version':__version__,
             'notes':args.notes[:3000],'packages':packages}
    private=serialization.load_pem_private_key(args.key.read_bytes(),password=None)
    raw=json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode()
    envelope={'signed':base64.b64encode(raw).decode(),'signature':base64.b64encode(private.sign(raw,padding.PKCS1v15(),hashes.SHA256())).decode()}
    decode_manifest(envelope)
    (args.output/'desktop-update.json').write_text(json.dumps(envelope),encoding='utf-8')
    if not args.base_url:
        checks=[]
        for path in sorted(args.output.iterdir()):
            if path.name in ('Pacoca-Setup.exe','desktop-update.json') or path.suffix=='.zip' and __version__ in path.name:
                checks.append(sha256(path)+'  '+path.name)
        (args.output/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    print('Signed release',__version__,flush=True)


if __name__=='__main__':main()
