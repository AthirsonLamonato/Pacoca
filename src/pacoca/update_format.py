"""Authenticated release format and bounded application-only ZIP validation."""
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from packaging.version import Version

from .update_trust import PUBLIC_KEY

APP_ID='pacoca-desktop'
MAX_PACKAGE=1_500_000_000
MAX_UNPACKED=2_500_000_000


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
    return digest.hexdigest()


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


def decode_manifest(envelope,key=PUBLIC_KEY):
    if isinstance(envelope,(bytes,str)):
        if len(envelope)>4_000_000:raise ValueError('Update manifest too large')
        envelope=json.loads(envelope,object_pairs_hook=unique_object)
    data=base64.b64decode(envelope['signed'],validate=True)
    signature=base64.b64decode(envelope['signature'],validate=True)
    if len(data)>2_000_000:raise ValueError('Update payload too large')
    public=rsa.RSAPublicNumbers(int.from_bytes(base64.b64decode(key['exponent']),'big'),
                               int.from_bytes(base64.b64decode(key['modulus']),'big')).public_key()
    public.verify(signature,data,padding.PKCS1v15(),hashes.SHA256())
    payload=json.loads(data,object_pairs_hook=unique_object)
    if payload.get('schema')!=1 or payload.get('app_id')!=APP_ID or payload.get('database_schema')!=1:
        raise ValueError('Incompatible release format or database schema')
    Version(payload['version'])
    if not re.fullmatch(r'\d+\.\d+\.\d+',payload['version']):raise ValueError('Stable versions only')
    if not isinstance(payload.get('packages'),list) or not 1<=len(payload['packages'])<=4:
        raise ValueError('Invalid package list')
    for package in payload['packages']:
        if package.get('kind') not in ('app','runtime') or not re.fullmatch('[a-f0-9]{64}',package.get('sha256','')):
            raise ValueError('Invalid release package')
        if not isinstance(package.get('size'),int) or not 0<package['size']<=MAX_PACKAGE:
            raise ValueError('Invalid release size')
        for name in ('runtime_id','from_runtime'):
            if not isinstance(package.get(name),str) or len(package[name])>128:raise ValueError('Invalid runtime identity')
    return payload


def application_path(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or value.startswith('/'):
        raise ValueError('Unsafe update path')
    parts=value.split('/')
    if any(p in ('','.','..') or p.endswith((' ','.')) or re.match(r'(?i)^(con|prn|aux|nul|com\d|lpt\d)(\.|$)',p) for p in parts):
        raise ValueError('Unsafe update path')
    if value not in ('Pacoca.exe','USAR-PACOCA.md','ALEXA.md') and not value.startswith('_internal/'):
        raise ValueError('An update cannot overwrite models or personal data')
    return PurePosixPath(value)


def validate_package(path,package,version):
    if Path(path).stat().st_size!=package['size'] or sha256(path)!=package['sha256']:
        raise ValueError('Update package checksum mismatch')
    with zipfile.ZipFile(path) as archive:
        if not 1<=len(archive.infolist())<=15000:raise ValueError('Invalid archive size')
        info=archive.getinfo('package.json')
        if info.file_size>2_000_000:raise ValueError('Package metadata too large')
        metadata=json.loads(archive.read(info),object_pairs_hook=unique_object)
        if metadata.get('version')!=version or metadata.get('runtime_id')!=package['runtime_id']:
            raise ValueError('Package identity mismatch')
        records=metadata.get('files',[])
        declared={r['path']:r for r in records}
        if len(declared)!=len(records):raise ValueError('Duplicate package path')
        folded=set();total=0
        for entry in archive.infolist():
            if entry.filename=='package.json':continue
            application_path(entry.filename)
            if entry.filename.casefold() in folded:raise ValueError('Case-insensitive path collision')
            folded.add(entry.filename.casefold())
            if stat.S_IFMT(entry.external_attr>>16)==stat.S_IFLNK or entry.is_dir():
                raise ValueError('Archive links or directory records are not supported')
            record=declared.get(entry.filename)
            if not record or record.get('size')!=entry.file_size:raise ValueError('Undeclared archive member')
            total+=entry.file_size
            if total>MAX_UNPACKED:raise ValueError('Unpacked update too large')
            digest=hashlib.sha256()
            with archive.open(entry) as stream:
                for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
            if digest.hexdigest()!=record.get('sha256'):raise ValueError('Archive member checksum mismatch')
        if len(folded)!=len(records):raise ValueError('Missing package member')
        if 'Pacoca.exe' not in declared:raise ValueError('The executable must be in the package')
        for value in metadata.get('remove',[]):
            application_path(value)
            if value.casefold() in folded:raise ValueError('A file cannot be replaced and removed together')
        if 'Pacoca.exe' in metadata.get('remove',[]):raise ValueError('Cannot remove executable')
        return metadata
