"""Create the publisher's local signing key once. Never put the private key in Git."""
import base64
import json
import os
from pathlib import Path
import subprocess

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT=Path(__file__).resolve().parents[1]


def main():
    private=ROOT/'.tools/update-signing-key.pem'
    public=ROOT/'packaging/update-public-key.json'
    if private.exists():
        key=serialization.load_pem_private_key(private.read_bytes(),password=None)
    elif public.exists():
        raise RuntimeError('An existing publisher key is already trusted. Supply its private key; do not silently rotate it.')
    else:
        key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
        private.parent.mkdir(exist_ok=True)
        private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        if os.name=='nt':
            import win32api,win32security,win32con
            token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY)
            sid=win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token,win32security.TokenUser)[0])
            subprocess.run(['icacls',str(private),'/inheritance:r','/grant:r','*'+sid+':F'],check=True,capture_output=True)
        else:private.chmod(0o600)
    numbers=key.public_key().public_numbers()
    def encoded(value):return base64.b64encode(value.to_bytes((value.bit_length()+7)//8,'big')).decode()
    data={'modulus':encoded(numbers.n),'exponent':encoded(numbers.e)}
    if public.exists() and json.loads(public.read_text())!=data:raise RuntimeError('Publisher keys do not match')
    public.write_text(json.dumps(data,indent=2)+'\n')
    source='"""Pinned publisher public key. The private key is never distributed."""\nPUBLIC_KEY = '+repr(data)+'\n'
    (ROOT/'src/pacoca/update_trust.py').write_text(source,encoding='utf-8')
    print('Publisher public key prepared. Private key remains in the ignored local tools directory.')


if __name__=='__main__':main()
