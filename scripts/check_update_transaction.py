"""Exercise the actual Windows helper with disposable, harmless test executables."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from pacoca.updates import render_helper,helper_encoded_command


def powershell(script,env):
    exe=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return subprocess.run([str(exe),'-NoProfile','-NonInteractive','-EncodedCommand',
        helper_encoded_command(script)],env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,capture_output=True,timeout=90)


def main():
    base=ROOT/'.test-data/update-helper'
    base.mkdir(parents=True,exist_ok=True)
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    numbers=private.public_key().public_numbers()
    def enc(n):return base64.b64encode(n.to_bytes((n.bit_length()+7)//8,'big')).decode()
    key={'modulus':enc(numbers.n),'exponent':enc(numbers.e)}
    executables={}
    for name,version in [('old','9.0.0'),('new','9.1.0')]:
        exe=base/(name+'.exe');source=base/(name+'.cs')
        source.write_text('''using System; using System.IO; using System.Text; using System.Diagnostics;
class Entry { static void Main(string[] args) {
for(int i=0;i<args.Length-1;i++) if(args[i]=="--update-health-file") {
string report="{\\"rendered\\":true,\\"version\\":\\"VERSION\\",\\"pid\\":"+Process.GetCurrentProcess().Id+"}";
File.WriteAllText(args[i+1],report,new UTF8Encoding(false));
} System.Threading.Thread.Sleep(1500);
}}'''.replace('VERSION',version),encoding='utf-8')
        # Explicitly replace only the fixture's own previous executable.
        exe.unlink(missing_ok=True)
        env={**os.environ,'PACOCA_FIXTURE_SOURCE':str(source),'PACOCA_FIXTURE_EXE':str(exe)}
        result=powershell("Add-Type -TypeDefinition (Get-Content -LiteralPath $env:PACOCA_FIXTURE_SOURCE -Raw -Encoding UTF8) -OutputType WindowsApplication -OutputAssembly $env:PACOCA_FIXTURE_EXE",env)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        executables[name]=exe.read_bytes()
    reports=[]
    for case in ('success','rollback','bad-signature'):
        folder=base/case;root=folder/"owner's app";data=folder/'data'
        transaction=data/'Updates/transaction-test'
        transaction.mkdir(parents=True,exist_ok=True)
        (root/'_internal').mkdir(parents=True,exist_ok=True)
        (root/'Pacoca.exe').write_bytes(executables['old'])
        (root/'_internal/probe.txt').write_text('old')
        (root/'_internal/obsolete.dll').write_bytes(b'old obsolete')
        models=root/'assets/models';models.mkdir(parents=True,exist_ok=True)
        (models/'keep.gguf').write_bytes(b'untouched model')
        version='9.1.0'
        files={'Pacoca.exe':executables['new'] if case!='rollback' else b'invalid executable',
               '_internal/probe.txt':b'new'}
        records=[{'path':p,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()} for p,b in files.items()]
        archive=data/'Updates/update.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p,b in files.items():z.writestr(p,b)
            z.writestr('package.json',json.dumps({'version':version,'runtime_id':'test','files':records,'remove':['_internal/obsolete.dll']}))
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        payload={'schema':1,'app_id':'pacoca-desktop','database_schema':1,'version':version,
            'packages':[{'kind':'runtime','from_runtime':'*','runtime_id':'test','sha256':digest,'size':archive.stat().st_size}]}
        raw=json.dumps(payload).encode()
        signature=private.sign(raw,padding.PKCS1v15(),hashes.SHA256())
        if case=='bad-signature':signature=b'\0'*len(signature)
        manifest=transaction/'manifest.json';manifest.write_text(json.dumps({
            'signed':base64.b64encode(raw).decode(),'signature':base64.b64encode(signature).decode()}))
        job=transaction/'job.json';job.write_text(json.dumps({'install_root':str(root),'data_root':str(data),
            'transaction':str(transaction),'manifest':str(manifest),'archive':str(archive),
            'package_hash':digest,'version':version,'pid':99999999}))
        result=powershell(render_helper(root,data,key),{**os.environ,'PACOCA_UPDATE_JOB':str(job)})
        receipt=json.loads((data/'Updates/last-result.json').read_text(encoding='utf-8-sig'))
        print(json.dumps({'case':case,'exit':result.returncode,'receipt':receipt},ensure_ascii=True),flush=True)
        expected={'success':'installed','rollback':'rolled_back','bad-signature':'failed'}[case]
        assert receipt['status']==expected,receipt
        if case=='success':
            assert (root/'Pacoca.exe').read_bytes()==executables['new']
            assert not (root/'_internal/obsolete.dll').exists()
        else:
            assert (root/'Pacoca.exe').read_bytes()==executables['old']
            assert (root/'_internal/probe.txt').read_text()=='old'
        assert (models/'keep.gguf').read_bytes()==b'untouched model'
        reports.append({'case':case,'status':receipt['status'],'models_preserved':True})
    (ROOT/'.test-data/evidence/update-transactions.json').write_text(json.dumps(reports,indent=2))


if __name__=='__main__':main()
